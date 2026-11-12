# Vendored PayPal Python SDK

`paypal-2.29-py3-none-any.whl` is the APIMatic-generated PayPal Server SDK for Python, built unmodified from
https://github.com/context-plugins/paypal-python-sdk at commit `143e57f2a3729d7df3727386b8c9ddf023d9a5df`
(MIT licence, see `PAYPAL_SDK_LICENSE`). It is vendored so Docker builds do not need `git` or GitHub access.

`pyproject.toml` still names the upstream git commit, so `pip install -e .` outside Docker resolves the same code.
Rebuild: `git clone <repo> && cd paypal-python-sdk && git checkout 143e57f2 && uv build --wheel -o ../vendor`.
