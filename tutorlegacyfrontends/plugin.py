from __future__ import annotations

import os
from glob import glob

import click
import importlib_resources
from tutor import hooks
from tutor.hooks import priorities

from .__about__ import __version__


########################################
# PATCH CONTENTS (the important stuff)
########################################

BUILD_PRODUCTION_ASSETS = """
# Build & collect production assets. By default, only assets from the default theme
# will be processed. This makes the docker image lighter and faster to build.
RUN npm run postinstall  # Postinstall artifacts are stuck in nodejs-requirements layer. Create them here too.
RUN npm run compile-sass -- --skip-themes
RUN npm run webpack

# Now that the default theme is built, build any custom themes
COPY --chown=app:app ./themes/ /openedx/themes
RUN npm run compile-sass -- --skip-default
"""

BUILD_DEVELOPMENT_ASSETS = """
# Recompile static assets: in development mode all static assets are stored in edx-platform,
# and the location of these files is stored in webpack-stats.json. If we don't recompile
# static assets, then production assets will be served instead.
RUN rm -r /openedx/staticfiles && \
    mkdir /openedx/staticfiles && \
    npm run build-dev
"""

hooks.Filters.ENV_PATCHES.add_item(
    ("openedx-dockerfile-pre-assets", BUILD_PRODUCTION_ASSETS),
    # In Tutor's Dockerfile, this patch point used to exist *before* the
    # production assets build.
    # So, for bacwards compatibility for users of this patch, we insert the
    # production assets build as the very *last* part of the patch.
    priority=100,
)

hooks.Filters.ENV_PATCHES.add_item(
    ("openedx-dev-dockerfile-post-python-requirements", BUILD_DEVELOPMENT_ASSETS),
    # In Tutor's Dockerfile, this patch point used to exist *after* the
    # development assets build.
    # So, for bacwards compatibility for users of this patch, we insert the
    # development assets build as the very *first* part of the patch.
    priority=1,
)


########################################
# CONFIGURATION
########################################

hooks.Filters.CONFIG_DEFAULTS.add_items(
    [
        # Add your new settings that have default values here.
        # Each new setting is a pair: (setting_name, default_value).
        # Prefix your setting names with 'LEGACYFRONTENDS_'.
        ("LEGACYFRONTENDS_VERSION", __version__),
    ]
)

hooks.Filters.CONFIG_UNIQUE.add_items(
    [
        # Add settings that don't have a reasonable default for all users here.
        # For instance: passwords, secret keys, etc.
        # Each new setting is a pair: (setting_name, unique_generated_value).
        # Prefix your setting names with 'LEGACYFRONTENDS_'.
        # For example:
        ### ("LEGACYFRONTENDS_SECRET_KEY", "{{ 24|random_string }}"),
    ]
)

hooks.Filters.CONFIG_OVERRIDES.add_items(
    [
        # Danger zone!
        # Add values to override settings from Tutor core or other plugins here.
        # Each override is a pair: (setting_name, new_value). For example:
        ### ("PLATFORM_NAME", "My platform"),
    ]
)


########################################
# INITIALIZATION TASKS
########################################

# To add a custom initialization task, create a bash script template under:
# tutorlegacyfrontends/templates/legacyfrontends/tasks/
# and then add it to the MY_INIT_TASKS list. Each task is in the format:
# ("<service>", ("<path>", "<to>", "<script>", "<template>"))
MY_INIT_TASKS: list[tuple[str, tuple[str, ...]]] = [
    # For example, to add LMS initialization steps, you could add the script template at:
    # tutorlegacyfrontends/templates/legacyfrontends/tasks/lms/init.sh
    # And then add the line:
    ### ("lms", ("legacyfrontends", "tasks", "lms", "init.sh")),
]


# For each task added to MY_INIT_TASKS, we load the task template
# and add it to the CLI_DO_INIT_TASKS filter, which tells Tutor to
# run it as part of the `init` job.
for service, template_path in MY_INIT_TASKS:
    full_path: str = str(
        importlib_resources.files("tutorlegacyfrontends")
        / os.path.join("templates", *template_path)
    )
    with open(full_path, encoding="utf-8") as init_task_file:
        init_task: str = init_task_file.read()
    hooks.Filters.CLI_DO_INIT_TASKS.add_item((service, init_task))


########################################
# DOCKER IMAGE MANAGEMENT
########################################


# Images to be built by `tutor images build`.
# Each item is a quadruple in the form:
#     ("<tutor_image_name>", ("path", "to", "build", "dir"), "<docker_image_tag>", "<build_args>")
hooks.Filters.IMAGES_BUILD.add_items(
    [
        # To build `myimage` with `tutor images build myimage`,
        # you would add a Dockerfile to templates/legacyfrontends/build/myimage,
        # and then write:
        ### (
        ###     "myimage",
        ###     ("plugins", "legacyfrontends", "build", "myimage"),
        ###     "docker.io/myimage:{{ LEGACYFRONTENDS_VERSION }}",
        ###     (),
        ### ),
    ]
)


# Images to be pulled as part of `tutor images pull`.
# Each item is a pair in the form:
#     ("<tutor_image_name>", "<docker_image_tag>")
hooks.Filters.IMAGES_PULL.add_items(
    [
        # To pull `myimage` with `tutor images pull myimage`, you would write:
        ### (
        ###     "myimage",
        ###     "docker.io/myimage:{{ LEGACYFRONTENDS_VERSION }}",
        ### ),
    ]
)


# Images to be pushed as part of `tutor images push`.
# Each item is a pair in the form:
#     ("<tutor_image_name>", "<docker_image_tag>")
hooks.Filters.IMAGES_PUSH.add_items(
    [
        # To push `myimage` with `tutor images push myimage`, you would write:
        ### (
        ###     "myimage",
        ###     "docker.io/myimage:{{ LEGACYFRONTENDS_VERSION }}",
        ### ),
    ]
)


########################################
# TEMPLATE RENDERING
# (It is safe & recommended to leave
#  this section as-is :)
########################################

hooks.Filters.ENV_TEMPLATE_ROOTS.add_items(
    # Root paths for template files, relative to the project root.
    [
        str(importlib_resources.files("tutorlegacyfrontends") / "templates"),
    ]
)

hooks.Filters.ENV_TEMPLATE_TARGETS.add_items(
    # For each pair (source_path, destination_path):
    # templates at ``source_path`` (relative to your ENV_TEMPLATE_ROOTS) will be
    # rendered to ``source_path/destination_path`` (relative to your Tutor environment).
    # For example, ``tutorlegacyfrontends/templates/legacyfrontends/build``
    # will be rendered to ``$(tutor config printroot)/env/plugins/legacyfrontends/build``.
    [
        ("legacyfrontends/build", "plugins"),
        ("legacyfrontends/apps", "plugins"),
    ],
)


########################################
# CUSTOM JOBS (a.k.a. "do-commands")
########################################

# A job is a set of tasks, each of which run inside a certain container.
# Jobs are invoked using the `do` command, for example: `tutor local do importdemocourse`.
# A few jobs are built in to Tutor, such as `init` and `createuser`.
# You can also add your own custom jobs:


# To add a custom job, define a Click command that returns a list of tasks,
# where each task is a pair in the form ("<service>", "<shell_command>").
# For example:
### @click.command()
### @click.option("-n", "--name", default="plugin developer")
### def say_hi(name: str) -> list[tuple[str, str]]:
###     """
###     An example job that just prints 'hello' from within both LMS and CMS.
###     """
###     return [
###         ("lms", f"echo 'Hello from LMS, {name}!'"),
###         ("cms", f"echo 'Hello from CMS, {name}!'"),
###     ]


# Then, add the command function to CLI_DO_COMMANDS:
## hooks.Filters.CLI_DO_COMMANDS.add_item(say_hi)

# Now, you can run your job like this:
#   $ tutor local do say-hi --name="Kyle McCormick"


#######################################
# CUSTOM CLI COMMANDS
#######################################

# Your plugin can also add custom commands directly to the Tutor CLI.
# These commands are run directly on the user's host computer
# (unlike jobs, which are run in containers).

# To define a command group for your plugin, you would define a Click
# group and then add it to CLI_COMMANDS:


### @click.group()
### def legacyfrontends() -> None:
###     pass


### hooks.Filters.CLI_COMMANDS.add_item(legacyfrontends)


# Then, you would add subcommands directly to the Click group, for example:


### @legacyfrontends.command()
### def example_command() -> None:
###     """
###     This is helptext for an example command.
###     """
###     print("You've run an example command.")


# This would allow you to run:
#   $ tutor legacyfrontends example-command
