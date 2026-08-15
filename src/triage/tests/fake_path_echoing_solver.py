#!/usr/bin/env python3
"""Fake solver that echoes its own invoked file path back into a parse-error
style message -- the way real solvers (e.g. cvc5) do. Used to regression-test
dedup.py's strip_own_filename() false-positive guard (see #64): a
creduce-mangled or upstream-derived filename can coincidentally contain a
crash signature substring (e.g. "...resetAssertions..." matching
"Assertion"), which must not be misread as a real crash."""
import sys

print(f'(error "Parse Error: {sys.argv[-1]}:1.1: unexpected token")')
