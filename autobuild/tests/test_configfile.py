#!/usr/bin/env python2
# $LicenseInfo:firstyear=2010&license=mit$
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
#
# Integration test to exercise the config file reading/writing
#

from __future__ import absolute_import
import unittest
import os
import sys
from .baseline_compare import AutobuildBaselineCompare
from autobuild import configfile
from autobuild.executable import Executable
from .basetest import BaseTest


class TestConfigFile(BaseTest, AutobuildBaselineCompare):

    def setUp(self):
        BaseTest.setUp(self)

    def test_configuration_simple(self):
        tmp_file = self.get_tmp_file(4)
        config = configfile.ConfigurationDescription(tmp_file)
        package = configfile.PackageDescription('test')
        config.package_description = package
        platform = configfile.PlatformDescription()
        platform.build_directory = '.'
        build_cmd = Executable(command="gcc", options=['-wall'])
        build_configuration = configfile.BuildConfigurationDescription()
        build_configuration.build = build_cmd
        platform.configurations['common'] = build_configuration
        config.package_description.platforms['common'] = platform
        config.save()

        reloaded = configfile.ConfigurationDescription(tmp_file)
        assert reloaded.package_description.platforms['common'].build_directory == '.'
        assert reloaded.package_description.platforms['common'].configurations['common'].build.get_command(
        ) == 'gcc'

    def test_configuration_inherit(self):
        tmp_file = self.get_tmp_file(4)
        config = configfile.ConfigurationDescription(tmp_file)
        package = configfile.PackageDescription('test')
        config.package_description = package

        common_platform = configfile.PlatformDescription()
        common_platform.build_directory = 'common_build'
        common_cmd = Executable(command="gcc", options=['-wall'])
        common_configuration = configfile.BuildConfigurationDescription()
        common_configuration.build = common_cmd
        common_platform.configurations['common'] = common_configuration
        config.package_description.platforms['common'] = common_platform

        darwin_platform = configfile.PlatformDescription()
        darwin_platform.build_directory = 'darwin_build'
        darwin_cmd = Executable(command="clang", options=['-wall'])
        darwin_configuration = configfile.BuildConfigurationDescription()
        darwin_configuration.build = darwin_cmd
        darwin_platform.configurations['darwin'] = darwin_configuration
        config.package_description.platforms['darwin'] = darwin_platform

        config.save()

        reloaded = configfile.ConfigurationDescription(tmp_file)
        assert reloaded.get_platform(
            'common').build_directory == 'common_build'
        assert reloaded.get_platform(
            'darwin').build_directory == 'darwin_build'
        # check that we fall back to the 32 bit version if no 64 bit is found
        assert reloaded.get_platform(
            'darwin64').build_directory == 'darwin_build'

    def tearDown(self):
        self.cleanup_tmp_file()
        BaseTest.tearDown(self)


if __name__ == '__main__':
    unittest.main()
