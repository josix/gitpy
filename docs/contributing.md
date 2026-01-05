### Step 1. Fork this repository to your GitHub

### Step 2. Clone the repository from your GitHub

```sh
git clone https://github.com/[YOUR GITHUB ACCOUNT]/gitpy.git
```

### Step 3. Add this repository to the remote in your local repository

```sh
git remote add upstream "https://github.com/josix/gitpy"
```

You can pull the latest code in main branch through `git pull upstream main` afterward.

### Step 4. Check out a branch for your new feature

```sh
git checkout -b [YOUR FEATURE]
```

### Step 5. Install prerequisite

```sh
# Install uv (recommended)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or with pipx
python -m pip install pipx
python -m pipx install uv invoke
python -m pipx ensurepath
```

* [uv](https://docs.astral.sh/uv/): for package and environment management
* [invoke](https://github.com/pyinvoke/invoke): for task management

### Step 6. Create your local Python virtual environment and install dependencies

```sh
uv sync --group dev
# Or use invoke task:
uv run inv env.init-dev
```

### Step 7. Work on your new feature
Note that this project follows [conventional-commit](https://www.conventionalcommits.org/en/v1.0.0/) and bumps version based on it. Use the following command to commit your changes.

```sh
uv run inv git.commit
# Or use commitizen directly:
uv run cz commit
```

### Step 8. Run test cases
Make sure all test cases pass.

```sh
uv run pytest tests/ -v
# Or use invoke task:
uv run inv test
```

### Step 9. Run test coverage
Check the test coverage and see where you can add test cases.

```sh
uv run pytest --cov=gitpy tests/
# Or use invoke task:
uv run inv test.cov
```

### Step 10. Reformat source code

Format your code with `ruff`.

```sh
uv run ruff format .
# Or use invoke task:
uv run inv style.reformat
```

### Step 11. Run style check
Make sure your coding style passes all enforced linters.

```sh
uv run ruff check .
uv run mypy gitpy tests
# Or use invoke task:
uv run inv style
```

### Step 12. Run security check

Ensure the packages installed are secure, and no major vulnerability is introduced

```sh
uv run bandit -r gitpy
uv run pip-audit
# Or use invoke task:
uv run inv secure
```

### Step 13. Create a Pull Request and celebrate 🎉
