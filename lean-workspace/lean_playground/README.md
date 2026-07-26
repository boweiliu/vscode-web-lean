# lean_playground

A small Lean 4 playground with two runnable programs, managed by Lake.

## Programs

| Source | Executable | What it does |
|---|---|---|
| `HelloWorld.lean` | `hello` | Prints `Hello, world!` |
| `Fibonacci.lean` | `fib` | Reads an integer `n` from stdin, prints the `n`-th Fibonacci number (0-indexed) |

## Building

```bash
lake build          # build both executables
```

## Running

```bash
lake exe hello      # -> Hello, world!

echo 10 | lake exe fib    # -> 55
echo 100 | lake exe fib   # -> 354224848179261915075
```

`fib` uses Lean's arbitrary-precision `Nat`, so large indices (e.g. `fib 1000`)
work without overflow. Non-numeric input prints an error and exits with code 1.

The compiled binaries also live at `.lake/build/bin/hello` and
`.lake/build/bin/fib` if you prefer to run them directly.
