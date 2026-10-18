# Smartwatch swimming data: rights and annotation qualification

Verified 2026-10-18 at the primary author repository:
<https://github.com/brunnergino/swimming-recognition-lap-counting/tree/468ee355675b51fb3b9ad9d992ef7b807ae1af4f>.

The complete Git tree has 209 files, including 206 CSV sessions and README.md,
but no LICENSE file. The README contains no licence grant. The former registry
MIT attribution is unsupported by this primary source. Public access alone does
not grant redistribution. Classification: **tier C, source-only**, with local
validation permitted and no rehosting pending author clarification.

The README links the author's public code folder through <http://bit.ly/2VGEeWN>,
resolving to
<https://drive.google.com/drive/folders/1vokHwmLkQr2Kw1KStWbec_ru5XAtveva>.
Its code subfolder has no displayed licence file either. No account was used.

## Labels omitted from the repository README

The README lists 0–5 only. Released data also contain 44,047 samples of code 6
and 77,943 samples of code -1. The author-linked `code/constants.py` explicitly
names them `Kick` and `Unknown`, respectively. The builder downloads this small
file as **inert text**, never executes it, and checks SHA256
`e92a4d38b0a9c244fd0d66fbc98cc0d5b6119673f61385dd460e20e88f2f903f`:
<https://drive.usercontent.google.com/download?id=19ncqFANBR2aCAxOryMPyEVjnhPBYy9j8&export=download&confirm=t>.

Thus -1 remains unavailable ground truth; codes 0 Null (other activity including
rest), 5 Turn, and 6 Kick remain scored classes. No labels are rounded, merged,
replaced with filename styles, or inferred from sensor values.
