# Security

Folio Lab is a local application. The hub and every analysis module listen on `127.0.0.1` only and refuse requests
from other origins, so nothing is reachable from the network unless you change this yourself. Do not expose the
ports to a network or the internet. The modules read and run on files you open, and the LaTeX compiler runs on
your documents.

What the application downloads, and when:

- `setup.ps1` downloads Node.js (nodejs.org) and MiKTeX (miktex.org), and installs Python packages from PyPI.
- MiKTeX may download missing LaTeX packages the first time a document uses them.
- `tools/fetch_optional_data.py` downloads reference data from the original publishers, but only when you run it.
- In the Elementrechner molecule designer, the PubChem name look-up sends the drawn structure (SMILES only) to
  pubchem.ncbi.nlm.nih.gov. It runs only when you ask for a name.

The analysis modules make no other network requests. Your measurement files and results stay on your computer.

To report a vulnerability, open a GitHub issue that does not include exploit details, and ask for a private contact,
or use GitHub's private vulnerability reporting for this repository if it is enabled.
