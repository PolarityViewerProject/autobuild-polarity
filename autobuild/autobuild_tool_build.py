#!/usr/bin/python
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

"""
Builds the source for a package.
"""

import os

# autobuild modules:
import common
import copy
import autobuild_base
import configfile
import logging
from common import AutobuildError
from autobuild_tool_configure import _configure_a_configuration


logger = logging.getLogger('autobuild.build')


# Add autobuild/bin to path.
os.environ["PATH"] = os.pathsep.join([os.environ["PATH"], os.path.normpath(
    os.path.join(os.path.dirname(__file__), os.pardir, "bin"))])


class BuildError(AutobuildError):
    pass
    

class AutobuildTool(autobuild_base.AutobuildBase):
    def get_details(self):
        return dict(name=self.name_from_file(__file__),
                    description="Builds platform targets.")

    def register(self, parser):
        parser.usage = """%(prog)s [-h] [--no-configure] [--config-file CONFIG_FILE] [-a]
                       [-c CONFIGURATION] [--dry-run] -- [OPT [OPT ...]]"""
        parser.description = "build the current package and copy its output artifacts into the build directory for use by the 'autobuild package' command."
        parser.add_argument('--config-file',
                            dest='config_file',
                            default=configfile.AUTOBUILD_CONFIG_FILE,
                            help='(defaults to $AUTOBUILD_CONFIG_FILE or "autobuild.xml")')
        parser.add_argument('--no-configure',
                            dest='do_not_configure',
                            default=False,
                            action="store_true",
                            help="do not configure before building")
        parser.add_argument('build_extra_arguments', nargs="*", metavar='OPT',
                            help="an option to pass to the build command")
        parser.add_argument('--all', '-a', dest='all', default=False, action="store_true",
                            help="build all configurations")
        parser.add_argument('--configuration', '-c', nargs='?', action="append", dest='configurations', 
                            help="build a specific build configuration\n(may be specified as comma separated values in $AUTOBUILD_CONFIGURATION)",
                            metavar='CONFIGURATION',
                            default=self.configurations_from_environment())
        parser.add_argument('--id', '-i', dest='build_id', help='unique build identifier')
        parser.add_argument('--clean-only',
                            action="store_true",
                            default=True if 'AUTOBUILD_CLEAN_ONLY' in os.environ else False,
                            dest='clean_only',
                            help="require that the build not depend on packages that are local or lack metadata\n"
                            + "  may also be set by defining the environment variable AUTOBUILD_CLEAN_ONLY"
                            )
        parser.add_argument('--install-dir',
                            default=None,
                            dest='select_dir',          # see common.select_directories()
                            help='Where installed files were unpacked.')
        parser.add_argument('--installed-manifest',
                            default=configfile.INSTALLED_CONFIG_FILE,
                            dest='installed_filename',
                            help='The file used to record what is installed.')

    def run(self, args):
        build_id = common.establish_build_id(args.build_id)  # sets id (even if not specified),
                                                             # and stores in the AUTOBUILD_BUILD_ID environment variable
        config = configfile.ConfigurationDescription(args.config_file)
        platform = common.get_current_platform()
        current_directory = os.getcwd()
        if args.clean_only:
            logger.info("building with --clean-only required")
        try:
            configure_first = not args.do_not_configure
            build_configurations = common.select_configurations(args, config, "building for")
            if not build_configurations:
                logger.warn("no applicable build configurations found, autobuild cowardly refuses to build nothing!")
                logger.warn("did you remember to mark a build command as default? try passing 'default=true' to your 'autobuild edit build' command")
            # packages were written into 'packages' subdir of build directory by default
            install_dirs = common.select_directories(args, config, "metadata", "getting installed packages",
                                                     lambda cnf:
                                                     os.path.join(config.get_build_directory(cnf, platform), "packages"))

            # get the absolute paths to the install dir and installed-packages.xml file
            install_dir = os.path.realpath(install_dirs[0])

            for build_configuration in build_configurations:
                build_directory = config.make_build_directory(build_configuration, args.dry_run)
                logger.debug("building in %s" % build_directory)
                if not args.dry_run:
                    os.chdir(build_directory)
                if configure_first:
                    result = _configure_a_configuration(config, build_configuration,
                                                        args.build_extra_arguments, args.dry_run)
                    if result != 0:
                        raise BuildError("configuring default configuration returned %d" % result)
                result = _build_a_configuration(config, build_configuration,
                                                args.build_extra_arguments, args.dry_run)
                # always make clean copy of the build metadata regardless of result
                metadata_file_name = configfile.PACKAGE_METADATA_FILE
                logger.debug("metadata file name: %s" % metadata_file_name)
                if not args.dry_run and os.path.exists(metadata_file_name):
                    os.unlink(metadata_file_name)
                if result != 0:
                    raise BuildError("building default configuration returned %d" % result)

                # Create the metadata record for inclusion in the package
                metadata_file = configfile.MetadataDescription(path=metadata_file_name, create_quietly=True)
                # include the package description from the configuration
                metadata_file.package_description = config.package_description
                metadata_file.package_description.platforms = None  # omit data on platform configurations
                metadata_file.platform = platform
                metadata_file.configuration = build_configuration.name
                metadata_file.build_id = build_id
                # get the record of any installed packages
                logger.debug("installed files in " + args.installed_filename)
                # load the list of already installed packages
                installed_pathname = os.path.join(install_dir, args.installed_filename)
                if os.path.exists(installed_pathname):
                    metadata_file.add_dependencies(installed_pathname)
                else:
                    logger.debug("no installed files found (%s)" % installed_pathname)
                if args.clean_only and metadata_file.dirty:
                    raise BuildError("Build depends on local or legacy installables\n"
                               +"  use 'autobuild install --list-dirty' to see problem packages\n"
                               +"  rerun without --clean-only to allow building anyway")
                if not args.dry_run:
                    metadata_file.save()
        finally:
            os.chdir(current_directory)


def build(config, build_configuration_name, extra_arguments=[]):
    """
    Execute the platform build command for the named build configuration.

    A special 'common' platform may be defined which can provide parent commands for the build
    command using the inheritence mechanism described in the 'executable' package.  The
    working platform's build configuration will be matched to the build configuration in common with
    the same name if it exists.  To be built, a build configuration must be defined in the working
    platform though it does not need to contain any actual commands if it is desired that the common
    commands be used.  Build configurations defined in the common platform but not the working
    platform are not built.
    """
    build_configuration = config.get_build_configuration(build_configuration_name)
    return _build_a_configuration(config, build_configuration, extra_arguments)


def _build_a_configuration(config, build_configuration, extra_arguments, dry_run=False):
    try:
        common_build_configuration = \
            config.get_build_configuration(build_configuration.name, 'common')
        parent_build = common_build_configuration.build
    except Exception, e:
        if logger.getEffectiveLevel() <= logging.DEBUG:
            logger.exception(e)
        logger.debug('no common platform found')
        parent_build = None
    if build_configuration.build is not None:
        build_executable = copy.copy(build_configuration.build)
        build_executable.parent = parent_build
    elif parent_build is not None:
        logger.info('no build executable defined; falling back to parent')
        build_executable = parent_build
    else:
        logger.info('no build executable defined; doing nothing')
        return 0
    logger.info('executing build command %s', build_executable.__str__(extra_arguments))
    if not dry_run:
        return build_executable(extra_arguments, common.get_autobuild_environment())
    else:
        return 0
