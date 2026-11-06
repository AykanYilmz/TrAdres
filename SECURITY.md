# Security policy

## Supported versions

TrAdres is young. Only the latest release gets security fixes.

## Report a problem

Please do not open a public issue for a security problem. Send an email to
**aykan010@outlook.com** with the steps to see the problem. I will answer as
soon as I can, and I will tell you when a fix is ready.

**Do not include a real person's address** in your report. Use made-up numbers
and street names.

## What counts as a security problem

- Input that makes `parse` or `tradres parse-csv` hang, or use far too much
  memory or CPU.
- A CSV result cell that a spreadsheet can run as a formula. TrAdres adds `'`
  before new cells that start with `=`, `+`, `-` or `@`. It does not change the
  columns of the input file.
- A package that sends data over the network. TrAdres works offline and must
  never do this.

A wrong parsing result is not a security problem. Please use the "Wrongly
parsed address" issue form for it.

## The local demo

`python -m demo` is a development tool. It listens on `127.0.0.1` only. It is not
in the package, and it should not run on a public server.
