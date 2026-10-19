# OpenRouter key setup (WSL / Windows)

This configures a **local secret** for future authorized OpenRouter runs.
Creating `.env` does **not** authorize inference.

## 1. Create the local file

From the experiment directory:

```bash
cd /home/user/projects/wellplot/experiments/nlp_gate_modernbert
cp .env.example .env
```

## 2. Paste your key (you do this locally)

Edit `.env` and set:

```bash
OPENROUTER_API_KEY=sk-or-v1-...your key...
```

Do not share the key with ChatGPT, Codex, or commit it.

### Windows (Notepad / Explorer)

1. Open `\\wsl$\Ubuntu\home\user\projects\wellplot\experiments\nlp_gate_modernbert\.env`
   (distro name may differ).
2. Paste the key after `OPENROUTER_API_KEY=`.
3. Save. Confirm `.env` is not staged in Git.

### WSL (terminal editor)

```bash
nano .env
# or: code .env
```

## 3. Verify presence only

```bash
cd /home/user/projects/wellplot/experiments/nlp_gate_modernbert
../nlp_slm_01/.venv/bin/python -c \
  "from nlp_gate_modernbert.decomposer_capability_02.api_key import inspect_api_key_presence; print(inspect_api_key_presence().to_json())"
```

Expected when configured:

```json
{"OPENROUTER_API_KEY_PRESENT": true, "env_var": "OPENROUTER_API_KEY"}
```

No length, prefix, or secret material is reported.

## 4. Explicit environment still wins

If `OPENROUTER_API_KEY` is already set in the shell, `.env` will **not** override it.

## 5. Still required for scientific calls

- Separate six-case Gemini **execution** authority
- Key present (`OPENROUTER_API_KEY_PRESENT=true`)

Key presence ≠ execution authorization.
