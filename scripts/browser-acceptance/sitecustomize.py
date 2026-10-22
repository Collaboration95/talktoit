"""Apply acceptance isolation to the official importer and spawned Python workers."""

import os

if os.environ.get("TTI_ACCEPTANCE_PRIVATE"):
    try:
        from safety import install

        install()
    except BaseException:
        # Python normally continues after sitecustomize errors; fail closed instead.
        os._exit(78)
