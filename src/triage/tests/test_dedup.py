#!/usr/bin/env python3
"""Unit + pipeline tests for dedup.py.

Solver-dependent tests use the fake solvers in tests/fake_target_solver.py,
tests/fake_oracle_solver.py and tests/fake_broken_solver.py (thin launchers
over tests/fake_solver_lib.py), a deterministic stand-in scripted via
(set-info ...) directives embedded in each fixture -- see fake_solver_lib.py
for the directive format. This keeps the suite hermetic and fast (no real
z3/cvc5 install required), and gives deterministic per-branch coverage of
dedup()'s logic that real solvers can't reliably be made to hit on demand.

RealSolverRegressionTest supplements this with a lightweight structural
sanity check against actual z3/cvc5 on the real .tar.gz archives committed
under tests/fixtures/archives/ (excepted from the repo's blanket *.tar.gz
gitignore rule), skipping itself only when the solvers aren't installed --
see that class's docstring.

RealCrashFixtureTests goes further for crashes specifically: it runs
dedup.confirm_crash() against real, committed, creduce-minimized crash
triggers (tests/fixtures/real_crashes/), so that check runs against real
z3/cvc5 on every checkout, not only when an archive happens to be present.
"""
import os
import shutil
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import dedup  # noqa: E402

TESTS_DIR = Path(__file__).resolve().parent
FAKE_TARGET_SOLVER = TESTS_DIR / "fake_target_solver.py"
FAKE_ORACLE_SOLVER = TESTS_DIR / "fake_oracle_solver.py"
FAKE_BROKEN_SOLVER = TESTS_DIR / "fake_broken_solver.py"

# each fake solver is directly executable (chmod +x + shebang) and named
# for its role, so target_cmd/oracle_cmd have distinct first tokens --
# exactly what dedup.py relies on to tell "z3 ..." and "cvc5 ..." apart.
TARGET_CMD = str(FAKE_TARGET_SOLVER)
ORACLE_CMD = str(FAKE_ORACLE_SOLVER)
TARGET_NAME = TARGET_CMD.split(" ")[0]
ORACLE_NAME = ORACLE_CMD.split(" ")[0]


def write_smt2(dir_path, name, directives=(), body="(declare-const x Int)\n(assert (> x 0))\n"):
    """Write a fixture .smt2 file with (set-info :key "value") directives
    the fake solver reads to decide its verdict at each pipeline stage."""
    lines = ["(set-logic ALL)", body.rstrip("\n")]
    for key, value in directives:
        lines.append(f'(set-info :{key} "{value}")')
    lines.append("(check-sat)")
    path = Path(dir_path) / name
    path.write_text("\n".join(lines) + "\n")
    return path


class PureFunctionTests(unittest.TestCase):
    """Tests for helpers that need no subprocess/solver at all."""

    def test_classify(self):
        self.assertEqual(dedup.classify(Path("incorrect-foo.smt2")), "soundness")
        self.assertEqual(dedup.classify(Path("crash-foo.smt2")), "crash")
        self.assertIsNone(dedup.classify(Path("other.smt2")))

    def test_crash_msg_known_signature(self):
        self.assertEqual(dedup.crash_msg("blah Segmentation fault blah"), "Segmentation fault")

    def test_crash_msg_unknown(self):
        self.assertEqual(dedup.crash_msg("nothing interesting here"), "unknown_crash")

    def test_datatype_bitstring(self):
        text = "(declare-const x Int)\n(declare-const b (_ BitVec 32))\n"
        self.assertEqual(dedup.datatype_bitstring(text), "010100")

    def test_datatype_bitstring_all_sorts(self):
        text = "Bool Int Real BitVec Array String"
        self.assertEqual(dedup.datatype_bitstring(text), "111111")

    def test_split_toplevel_forms_basic(self):
        forms = dedup.split_toplevel_forms("(a (b c)) (d)")
        self.assertEqual(forms, ["(a (b c))", "(d)"])

    def test_split_toplevel_forms_ignores_comment_parens(self):
        forms = dedup.split_toplevel_forms("; a comment with ( unbalanced parens\n(assert true)")
        self.assertEqual(forms, ["(assert true)"])

    def test_split_toplevel_forms_ignores_quoted_parens(self):
        forms = dedup.split_toplevel_forms('(assert (= s "a ) b"))')
        self.assertEqual(forms, ['(assert (= s "a ) b"))'])

    def test_split_toplevel_forms_pipe_quoted_symbol(self):
        forms = dedup.split_toplevel_forms("(declare-const |weird ( name| Int)")
        self.assertEqual(forms, ["(declare-const |weird ( name| Int)"])

    def test_parse_decl_name_declare_const(self):
        self.assertEqual(dedup.parse_decl_name("(declare-const x Int)"), "x")

    def test_parse_decl_name_nullary_declare_fun(self):
        self.assertEqual(dedup.parse_decl_name("(declare-fun y () Bool)"), "y")

    def test_parse_decl_name_non_nullary_declare_fun(self):
        self.assertIsNone(dedup.parse_decl_name("(declare-fun f (Int) Int)"))

    def test_parse_decl_name_not_a_declaration(self):
        self.assertIsNone(dedup.parse_decl_name("(assert (> x 0))"))

    def test_parse_define_name_nullary(self):
        self.assertEqual(dedup.parse_define_name("(define-fun x () Int 3)"), "x")

    def test_parse_define_name_non_nullary(self):
        self.assertIsNone(dedup.parse_define_name("(define-fun f ((a Int)) Int (+ a 1))"))

    def test_ground_formula_z3_style_model(self):
        orig = "(declare-const x Int)\n(assert (> x 0))\n(check-sat)\n"
        model = "(model\n  (define-fun x () Int 3)\n)\n"
        grounded = dedup.ground_formula(orig, model)
        self.assertIn("(define-fun x () Int 3)", grounded)
        self.assertNotIn("declare-const", grounded)
        self.assertEqual(grounded.count("(check-sat)"), 1)

    def test_ground_formula_cvc5_style_model(self):
        orig = "(declare-const x Int)\n(assert (> x 0))\n(check-sat)\n"
        model = "(\n(define-fun x () Int 3)\n)\n"
        grounded = dedup.ground_formula(orig, model)
        self.assertIn("(define-fun x () Int 3)", grounded)
        self.assertNotIn("declare-const", grounded)

    def test_ground_formula_leaves_unmodeled_symbols_declared(self):
        orig = "(declare-const x Int)\n(declare-const y Int)\n(assert (> x y))\n(check-sat)\n"
        model = "(model (define-fun x () Int 3))\n"
        grounded = dedup.ground_formula(orig, model)
        self.assertIn("(define-fun x () Int 3)", grounded)
        self.assertIn("(declare-const y Int)", grounded)

    def test_add_to_D_keeps_smaller_reproducer(self):
        D = []
        big_tup = ("z3", "crash", "Aborted", "000000", 500)
        small_tup = ("z3", "crash", "Aborted", "000000", 10)
        dedup.add_to_D(D, big_tup, Path("big.smt2"))
        dedup.add_to_D(D, small_tup, Path("small.smt2"))
        self.assertEqual(len(D), 1)
        self.assertEqual(D[0][0], small_tup)

    def test_add_to_D_distinct_bugs_both_kept(self):
        D = []
        dedup.add_to_D(D, ("z3", "crash", "Aborted", "000000", 10), Path("a.smt2"))
        dedup.add_to_D(D, ("z3", "crash", "Segmentation fault", "000000", 10), Path("b.smt2"))
        self.assertEqual(len(D), 2)


class CheckSolverInstalledTests(unittest.TestCase):
    def test_pass_on_default_sat(self):
        dedup.check_solver_installed(TARGET_CMD)  # must not raise/exit

    def test_fails_loudly_on_broken_install(self):
        with self.assertRaises(SystemExit) as ctx:
            dedup.check_solver_installed(str(FAKE_BROKEN_SOLVER))
        self.assertEqual(ctx.exception.code, dedup.ERR_USAGE)


class DedupSoundnessTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_solution_soundness_bug_confirmed(self):
        # target wrongly says sat; grounding its model and re-checking with
        # both solvers gives unsat -> target's model was invalid.
        path = write_smt2(self.dir, "incorrect-a.smt2", [
            ("fake-target-verdict", "sat"),
            ("fake-oracle-verdict", "unsat"),
            ("fake-model", "(define-fun x () Int 3)"),
            ("fake-target-check", "unsat"),
            ("fake-oracle-check", "unsat"),
        ])
        IN, D = dedup.dedup([path], TARGET_CMD, ORACLE_CMD)
        self.assertEqual(len(IN), 1)
        self.assertEqual(IN[0][0], (TARGET_NAME, "soundness", "solution", "010000", path.stat().st_size))
        self.assertEqual(D, IN)

    def test_refutational_soundness_bug_confirmed(self):
        # target wrongly says unsat; oracle's model grounds and both solvers
        # confirm sat -> target's refutation was wrong.
        path = write_smt2(self.dir, "incorrect-b.smt2", [
            ("fake-target-verdict", "unsat"),
            ("fake-oracle-verdict", "sat"),
            ("fake-model", "(define-fun x () Int 3)"),
            ("fake-target-check", "sat"),
            ("fake-oracle-check", "sat"),
        ])
        IN, D = dedup.dedup([path], TARGET_CMD, ORACLE_CMD)
        self.assertEqual(len(IN), 1)
        self.assertEqual(IN[0][0][1:3], ("soundness", "refutational"))

    def test_bug_is_in_oracle_not_target(self):
        # target says sat, oracle says unsat, but grounding confirms the
        # model is genuinely valid (both sat) -> the oracle was wrong, not
        # the target we're triaging, so nothing is reported.
        path = write_smt2(self.dir, "incorrect-c.smt2", [
            ("fake-target-verdict", "sat"),
            ("fake-oracle-verdict", "unsat"),
            ("fake-model", "(define-fun x () Int 3)"),
            ("fake-target-check", "sat"),
            ("fake-oracle-check", "sat"),
        ])
        IN, D = dedup.dedup([path], TARGET_CMD, ORACLE_CMD)
        self.assertEqual(IN, [])
        self.assertEqual(D, [])

    def test_validation_inconclusive_is_dropped(self):
        path = write_smt2(self.dir, "incorrect-d.smt2", [
            ("fake-target-verdict", "sat"),
            ("fake-oracle-verdict", "unsat"),
            ("fake-model", "(define-fun x () Int 3)"),
            ("fake-target-check", "sat"),
            ("fake-oracle-check", "unsat"),
        ])
        IN, D = dedup.dedup([path], TARGET_CMD, ORACLE_CMD)
        self.assertEqual(IN, [])

    def test_no_disagreement_is_dropped(self):
        path = write_smt2(self.dir, "incorrect-e.smt2", [
            ("fake-target-verdict", "sat"),
            ("fake-oracle-verdict", "sat"),
        ])
        IN, D = dedup.dedup([path], TARGET_CMD, ORACLE_CMD)
        self.assertEqual(IN, [])

    def test_target_inconclusive_is_dropped(self):
        path = write_smt2(self.dir, "incorrect-f.smt2", [
            ("fake-target-verdict", "unknown"),
            ("fake-oracle-verdict", "sat"),
        ])
        IN, D = dedup.dedup([path], TARGET_CMD, ORACLE_CMD)
        self.assertEqual(IN, [])


class DedupCrashTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_crash_trigger_confirmed(self):
        path = write_smt2(self.dir, "crash-a.smt2", [
            ("fake-target-verdict", "crash:Segmentation fault"),
        ])
        IN, D = dedup.dedup([path], TARGET_CMD, ORACLE_CMD)
        self.assertEqual(len(IN), 1)
        self.assertEqual(IN[0][0], (TARGET_NAME, "crash", "Segmentation fault", "010000", path.stat().st_size))

    def test_crash_no_longer_reproduces(self):
        path = write_smt2(self.dir, "crash-b.smt2", [
            ("fake-target-verdict", "sat"),
        ])
        IN, D = dedup.dedup([path], TARGET_CMD, ORACLE_CMD)
        self.assertEqual(IN, [])

    def test_unclassified_file_ignored(self):
        path = write_smt2(self.dir, "other-c.smt2", [
            ("fake-target-verdict", "crash:Aborted"),
        ])
        IN, D = dedup.dedup([path], TARGET_CMD, ORACLE_CMD)
        self.assertEqual(IN, [])

    def test_dedup_keeps_smaller_of_two_matching_crashes(self):
        small = write_smt2(self.dir, "crash-small.smt2", [
            ("fake-target-verdict", "crash:Aborted"),
        ])
        big = write_smt2(self.dir, "crash-big.smt2", [
            ("fake-target-verdict", "crash:Aborted"),
        ], body="(declare-const x Int)\n(assert (> x 0))\n" + "; padding\n" * 50)
        self.assertLess(small.stat().st_size, big.stat().st_size)
        IN, D = dedup.dedup(sorted([small, big]), TARGET_CMD, ORACLE_CMD)
        self.assertEqual(len(IN), 2)
        self.assertEqual(len(D), 1)
        self.assertEqual(D[0][1], small)


class MainEndToEndTest(unittest.TestCase):
    """Exercises the full CLI path: archive unpack -> dedup -> dedup_out
    write, the same path run.sh drives in production."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self._old_path = os.environ.get("PATH", "")

        # copy the fake solvers (+ their shared lib) into their own bin dir
        # on PATH, so target_cmd/oracle_cmd can be bare names -- matching
        # real invocations like "z3 ..."/"cvc5 ..." -- and so dedup.py's
        # target_cmd.split(" ")[0] naming of the dedup_out subdirectory
        # stays clean instead of embedding an absolute path.
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        for src in (FAKE_TARGET_SOLVER, FAKE_ORACLE_SOLVER, TESTS_DIR / "fake_solver_lib.py"):
            dst = bin_dir / src.name
            shutil.copy2(src, dst)
            dst.chmod(0o755)
        os.environ["PATH"] = str(bin_dir) + os.pathsep + self._old_path

        self.target_cmd = FAKE_TARGET_SOLVER.name
        self.oracle_cmd = FAKE_ORACLE_SOLVER.name

    def tearDown(self):
        os.environ["PATH"] = self._old_path
        self._tmp.cleanup()

    def test_main_writes_dedup_out(self):
        src_dir = self.tmp / "src"
        src_dir.mkdir()
        write_smt2(src_dir, "crash-a.smt2", [("fake-target-verdict", "crash:Segmentation fault")])
        write_smt2(src_dir, "incorrect-a.smt2", [
            ("fake-target-verdict", "sat"),
            ("fake-oracle-verdict", "unsat"),
            ("fake-model", "(define-fun x () Int 3)"),
            ("fake-target-check", "unsat"),
            ("fake-oracle-check", "unsat"),
        ])

        archive_path = self.tmp / "bugs-abc123-42.tar.gz"
        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(src_dir, arcname=".")

        out_dir = self.tmp / "dedup_out"
        dedup.main(str(archive_path), self.target_cmd, self.oracle_cmd, str(out_dir))

        run_out_dir = out_dir / f"bugs-abc123-42__{FAKE_TARGET_SOLVER.name}"
        self.assertTrue(run_out_dir.is_dir())
        produced = sorted(p.name for p in run_out_dir.iterdir())
        self.assertEqual(produced, ["crash-a.smt2", "incorrect-a.smt2"])

    def test_main_reports_error_on_bad_archive(self):
        out_dir = self.tmp / "dedup_out"
        with self.assertRaises(SystemExit) as ctx:
            dedup.main(str(self.tmp / "does-not-exist.tar.gz"), self.target_cmd, self.oracle_cmd, str(out_dir))
        self.assertEqual(ctx.exception.code, dedup.ERR_USAGE)


class RealSolverRegressionTest(unittest.TestCase):
    """Runs dedup() against real z3/cvc5 on the real .tar.gz archives
    committed under tests/fixtures/archives/ (excepted from the repo's
    blanket *.tar.gz gitignore rule -- see tests/fixtures/archives/README.md
    for provenance), checking the output is well-formed. This is
    deliberately not exact tuple-for-tuple matching against a recorded
    golden file: real solver output can shift across versions -- that
    determinism instead lives in the fake-solver tests above. Skips itself
    if z3/cvc5 aren't installed."""

    TARGET_CMD = "z3 model_validate=true"
    ORACLE_CMD = "cvc5 --check-models --check-proofs"
    ARCHIVES_DIR = TESTS_DIR / "fixtures" / "archives"

    def setUp(self):
        if shutil.which("z3") is None or shutil.which("cvc5") is None:
            self.skipTest("z3/cvc5 not installed")

    def test_dedup_output_is_well_formed(self):
        archives = sorted(self.ARCHIVES_DIR.glob("*.tar.gz"))
        self.assertTrue(archives, f"no fixture archives found in {self.ARCHIVES_DIR}")

        for archive in archives:
            with self.subTest(archive=archive.name), tempfile.TemporaryDirectory() as extract_dir:
                shutil.unpack_archive(archive, extract_dir)
                bug_files = sorted(Path(extract_dir).rglob("*.smt2"))
                IN, D = dedup.dedup(bug_files, self.TARGET_CMD, self.ORACLE_CMD)

                self.assertTrue(IN, f"{archive.name} confirmed no bugs -- fixture may need refreshing")
                self.assertLessEqual(len(D), len(IN))
                signatures = set()
                for tup, path in IN:
                    solver, kind, msg, dtype, size = tup
                    self.assertEqual(solver, "z3")
                    self.assertIn(kind, ("soundness", "crash"))
                    if kind == "soundness":
                        self.assertIn(msg, ("solution", "refutational"))
                    self.assertRegex(dtype, r"^[01]{6}$")
                    self.assertEqual(size, path.stat().st_size)  # path still lives in extract_dir here
                    signatures.add((solver, kind, msg, dtype))
                self.assertLessEqual(len(D), len(signatures))


class RealCrashFixtureTests(unittest.TestCase):
    """Confirms dedup.confirm_crash() against real, creduce-minimized crash
    triggers pulled from actual z3/cvc5 fuzzing runs (see
    tests/fixtures/real_crashes/README.md for provenance and how each was
    minimized with reduce.py). Unlike RealSolverRegressionTest, these are
    fixed, committed fixtures with a known expected crash signature, so --
    whenever the relevant solver happens to be installed -- this runs even
    on a fresh checkout, not just when a .tar.gz archive is present."""

    FIXTURES_DIR = TESTS_DIR / "fixtures" / "real_crashes"

    def _check(self, filename, target_cmd, expected_msg):
        solver = target_cmd.split(" ")[0]
        if shutil.which(solver) is None:
            self.skipTest(f"{solver} not installed")
        path = self.FIXTURES_DIR / filename
        self.assertEqual(dedup.confirm_crash(path, target_cmd), expected_msg)

    def test_z3_invalid_model_crash(self):
        self._check("z3-invalid-model.smt2", "z3 model_validate=true", "an invalid model was generated")

    def test_cvc5_assertion_crash(self):
        self._check("cvc5-assertion.smt2", "cvc5 --check-models --check-proofs", "ASSERTION")


if __name__ == "__main__":
    unittest.main()
