"""Keeping a failure report readable and free of secrets.

A browser journey types real passwords and real PINs. Its report has to say
enough to debug a failure and nothing that would put a credential into a
terminal, a log file or a pull request. These two functions are the whole
rule: `redact` replaces every known secret with a fixed marker, and
`leaked_secrets` is the check that proves it worked.

Stdlib only, so the host runner can import it without installing anything.
"""

REDACTED = '[redacted]'

# Shorter values are not worth masking: a two-character secret would turn
# ordinary words into marker soup and hide the failure instead of the secret.
MINIMUM_SECRET_LENGTH = 4


def maskable(secrets):
    """The secrets long enough to be worth replacing, longest first.

    Longest first matters: a secret that contains another one must be
    replaced before its substring, or the shorter replacement would cut the
    longer value in half and leave the remainder in the text.
    """
    return sorted(
        {value for value in secrets if len(value) >= MINIMUM_SECRET_LENGTH},
        key=len,
        reverse=True,
    )


def redact(text, secrets):
    """Return `text` with every known secret replaced by a fixed marker."""
    for value in maskable(secrets):
        text = text.replace(value, REDACTED)
    return text


def leaked_secrets(text, secrets):
    """The secrets still present in `text`, in the order they were given.

    A secret too short to mask is still reported when it appears, because a
    reader needs to know the report is unsafe even when this module has
    chosen not to rewrite it.
    """
    return [value for value in secrets if value and value in text]


def secret_values(dataset):
    """Every password and PIN inside a seeded dataset, wherever it sits.

    The runner never has to know the dataset's shape: anything stored under
    a `password` or `pin` key is a secret, at any depth.
    """
    found = []

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ('password', 'pin') and isinstance(value, str):
                    found.append(value)
                else:
                    walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(dataset)
    return found
