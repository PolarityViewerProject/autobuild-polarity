#!/usr/bin/env python2
"""\
@file   basetest.py
@author Nat Goodspeed
@date   2012-08-24
@brief  Define BaseTest, a base class for all individual test classes.
"""
# $LicenseInfo:firstyear=2012&license=mit$
# Copyright (c) 2010, Linden Research, Inc.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
# $/LicenseInfo$

from __future__ import print_function
import os
import sys
import errno
import re
import subprocess
import time
import shutil
import unittest
from contextlib import contextmanager
from cStringIO import StringIO

from autobuild import common


class BaseTest(unittest.TestCase):
    def setUp(self):
        self.this_dir = os.path.abspath(os.path.dirname(__file__))
        # Unfortunately, when we run tests, sys.argv[0] is (e.g.) "nosetests"!
        # So we can't just call get_autobuild_executable_path(); in fact that
        # function is untestable. Derive a suitable autobuild command relative
        # to this module's location. Note that this is OUR bin directory and
        # OUR autobuild.cmd script -- not anything created by pip.
        self.autobuild_bin = os.path.abspath(os.path.join(self.this_dir, os.pardir, os.pardir,
                                                          "bin", "autobuild"))
        if sys.platform.startswith("win"):
            self.autobuild_bin += ".cmd"

    def autobuild(self, *args, **kwds):
        """
        All positional args are collected as string arguments to the
        self.autobuild_bin command. If you want to pass additional arguments
        to subprocess.call(), pass them as keyword arguments; those are passed
        through.
        """
        command = (self.autobuild_bin,) + args
        rc = subprocess.call(command, **kwds)
        assert rc == 0, "%s => %s" % (' '.join(command), rc)

    # On Windows, need some retry logic wrapped around removing files (SIGHH)
    if not sys.platform.startswith("win"):
        remove = os.remove
    else:
        def remove(self, path):
            start = time.time()
            tries = 0
            while True:
                tries += 1
                try:
                    os.remove(path)
                except OSError as err:
                    if err.errno == errno.ENOENT:
                        return
                    if err.errno != errno.EACCES:
                        print("*** Unknown %s (errno %s): %s: %s" %
                              (err.__class__.__name__, err.errno, err, path))
                        sys.stdout.flush()
                        raise
                    if (time.time() - start) > 10:
                        print("*** remove(%r) timed out after %s retries" %
                              (path, tries))
                        sys.stdout.flush()
                        raise
                    time.sleep(1)

    def tearDown(self):
        pass


def clean_file(pathname):
    try:
        os.remove(pathname)
    except OSError as err:
        if err.errno != errno.ENOENT:
            print("*** Can't remove %s: %s" % (pathname, err), file=sys.stderr)
            # But no exception, we're still trying to clean up.


def clean_dir(pathname):
    try:
        shutil.rmtree(pathname)
    except OSError as err:
        # Nonexistence is fine.
        if err.errno != errno.ENOENT:
            print("*** Can't remove %s: %s" % (pathname, err), file=sys.stderr)


def assert_in(item, container):
    assert item in container, "%r not in %r" % (item, container)


def assert_not_in(item, container):
    assert item not in container, "%r should not be in %r" % (item, container)


def assert_found_in(regex, container):
    pattern = re.compile(regex)
    assert any(pattern.search(item)
               for item in container), "search failed for %r in %r" % (regex, container)


def assert_not_found_in(regex, container):
    pattern = re.compile(regex)
    assert not any(pattern.search(item)
                   for item in container), "search found %r in %r" % (regex, container)


@contextmanager
def exc(exceptionslist, pattern=None, without=None, message=None):
    """
    Usage:

    # succeeds
    with exc(ValueError):
        int('abc')

    # fails with AssertionError
    with exc(ValueError):
        int('123')

    # can specify multiple expected exceptions
    with exc((IndexError, ValueError)):
        int(''[0])
    with exc((IndexError, ValueError)):
        int('a'[0])

    # can match expected message, when exception type isn't sufficient
    with exc(Exception, 'badness'):
        raise Exception('much badness has occurred')

    # or can verify that exception message does NOT contain certain text
    with exc(Exception, without='string'):
        raise Exception('much int badness has occurred')
    """
    try:
        # run the body of the with block
        yield
    except exceptionslist as err:
        # okay, with block did raise one of the expected exceptions;
        # did the caller need the exception message to match a pattern?
        if pattern:
            if not re.search(pattern, str(err)):
                raise AssertionError("exception %s does not match '%s': '%s'" %
                                     (err.__class__.__name__, pattern, err))
        # or not to match a pattern?
        if without:
            if re.search(without, str(err)):
                raise AssertionError("exception %s should not match '%s': '%s'" %
                                     (err.__class__.__name__, without, err))
    else:
        # with block did not raise any of the expected exceptions: FAIL
        try:
            # did caller pass a tuple of exceptions?
            iter(exceptionslist)
        except TypeError:
            # just one exception class: use its name
            exceptionnames = exceptionslist.__name__
        else:
            # tuple of exception classes: format their names
            exceptionnames = "any of (%s)" % \
                ','.join(ex.__name__ for ex in exceptionslist)
        raise AssertionError(message or
                             ("with block did not raise " + exceptionnames))


def ExpectError(errfrag, expectation, exception=common.AutobuildError):
    """
    Usage:

    with ExpectError("text that should be in the exception", "Expected a bad thing to happen"):
        something(that, should, raise)

    replaces:

    try:
        self.options.package = ["no_such_package"]
        something(that, should, raise)
    except AutobuildError, err:
        assert_in("text that should be in the exception", str(err))
    else:
        assert False, "Expected a bad thing to happen"
    """
    return exc(exception, pattern=errfrag, message=expectation)


class CaptureStdout(object):
    """
    Usage:

    with CaptureStdout() as stream:
        print "something"
        print "something else"
    assert stream.getvalue() == "something\n" "something else\n"
    print "This will display on console, as before."

    Note that this does NOT capture output emitted by a child process -- only
    data written to sys.stdout.
    """

    def __enter__(self):
        self.stdout = sys.stdout
        sys.stdout = StringIO()
        return sys.stdout

    def __exit__(self, *exc_info):
        sys.stdout = self.stdout
