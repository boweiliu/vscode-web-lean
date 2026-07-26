/-!
Compute Fibonacci numbers.

Reads a single non-negative integer `n` from standard input and prints the
`n`-th Fibonacci number (0-indexed: fib 0 = 0, fib 1 = 1).

Lean's `Nat` is arbitrary precision, so large indices work without overflow.
-/

/-- Iterative Fibonacci carrying a running pair `(fib i, fib (i+1))`. -/
def fib (n : Nat) : Nat :=
  let rec go : Nat → Nat → Nat → Nat
    | 0,     a, _ => a
    | k + 1, a, b => go k b (a + b)
  go n 0 1

#guard fib 5 = 5
theorem guard_fib_5 : fib 5 = 5 := by rfl

def main : IO Unit := do
  IO.print (s!"Which fibonacci number do you want? btw F5 == 5.\n> ")
  let stdin ← IO.getStdin
  let line ← stdin.getLine
  let trimmed := line.trimAscii.toString
  match trimmed.toNat? with
  | some n => IO.println (fib n)
  | none =>
    IO.eprintln s!"Expected a non-negative integer on stdin, got: {repr trimmed}"
    IO.Process.exit 1
