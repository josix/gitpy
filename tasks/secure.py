from invoke import task

from tasks.common import VENV_PREFIX


@task
def check_package(ctx):
    """Check package security with pip-audit"""
    ctx.run(f"{VENV_PREFIX} pip-audit", warn=True)


@task
def bandit(ctx):
    """Check common software vulnerabilities (Use it as reference only)"""
    ctx.run(f"{VENV_PREFIX} bandit -r -iii -lll gitpy", pty=True)


@task(pre=[check_package, bandit], default=True)
def run(ctx):
    """Check security through pip-audit and bandit"""
    pass
