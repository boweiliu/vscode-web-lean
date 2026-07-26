/-!
Debug / diagnostic views for `rfl`, `decide`, `grind`, and `simp`.

Every "debug view" is a `set_option` (a compiler flag scoped to the next
declaration via `... in`) or a `#`-command. Nothing external is needed -- the
output lands in the InfoView's "All Messages" panel (or the terminal when you
run `lake env lean` on the file).

How to read the output in the browser IDE:
  * Open this file, open the InfoView (the ∀ button, top-right of the editor).
  * `set_option trace.X true in <decl>` attaches a trace tree to that decl;
    click on the decl (or open "All Messages") to see it.
  * `#reduce` / `#eval` / `#print` results also appear in "All Messages", or
    hover the `#` command line.

The running example is the iterative Fibonacci from `Fibonacci.lean`.
-/

def fib (n : Nat) : Nat :=
  let rec go : Nat → Nat → Nat → Nat
    | 0,     a, _ => a
    | k + 1, a, b => go k b (a + b)
  go n 0 1

/-! ## 1. `#reduce` -- see the normal form `rfl` computes

`rfl` works by asking the kernel to reduce both sides to a normal form. You
can't "trace" the kernel step-by-step, but `#reduce` shows you the ANSWER it
reaches -- i.e. what both sides of `fib 5 = 5 := rfl` collapse to. Cursor here
-> "All Messages" shows `5`. -/

#reduce fib 5           -- 5   (the kernel-reduced normal form)
#eval fib 5             -- 5   (the fast compiled path; same value, diff engine)

/-! ## 2. `simp only [fib, fib.go]` + rewrite trace -- the step-by-step unfolding

This is the closest thing to "watching `rfl` think". `simp only [fib, fib.go]`
unfolds the definition one recursion step at a time, and the rewrite trace
prints each step. This is exactly the ι-reduction chain the kernel does
silently for `rfl` (though simp leaves the `0 + 1`-style arithmetic unreduced).
Click the `example` line and read the trace in the InfoView. -/

set_option trace.Meta.Tactic.simp.rewrite true in
example : fib 5 = 5 := by simp only [fib, fib.go]

/-! ## 3. `grind` diagnostics ON FAILURE -- printed automatically

When `grind` fails it dumps its whole goal state: the asserted facts, the
equivalence classes it built, the E-matching patterns it tried, and any
threshold it hit. You don't need any option -- just let it fail. Uncomment the
theorem below to see the diagnostic dump (and the red error).

  theorem grind_fails : fib 5 = 5 := by grind

The key lines you'll see:
  [cutsat] Assignment satisfying linear constraints
    [assign] fib 5 := 1          <- grind treated `fib 5` as an OPAQUE symbol
This is why grind can't prove `fib 5 = 5`: it reasons symbolically and never
just EVALUATES the function. See TacticComparison notes below.

  (Left commented so this file compiles cleanly; uncomment to watch it fail.) -/

-- theorem grind_fails : fib 5 = 5 := by grind

-- Feed grind more rope -- unfold hints -- and watch it hit its round limit:
-- theorem grind_hint_fails : fib 3 = 2 := by grind [fib, fib.go]
-- With `grind [fib, fib.go]` the diagnostics DO show the unfolding chain -- look
-- under `[facts] Asserted facts` and `[eqc] Equivalence classes`:
--   fib 5 = fib.go 5 0 1 = fib.go 4 1 1 = ... = fib.go 1 3 5
-- and then it stops one step short of the base case, hitting:
--   [limit] maximum number of E-matching rounds has been reached (ematch := 5)

-- Raise the E-matching round budget with the `(ematch := N)` config so grind
-- reaches the base case and actually CLOSES the goal. The default is 5; this
-- goal needs 7. `maxRecDepth` must be bumped too or the deeper reduction
-- overflows. Turn on the eqc trace to watch the full chain complete:
--   fib.go 1 3 5 = fib.go 0 5 8 = 5   (the steps ematch:=5 couldn't reach)
set_option maxRecDepth 4000 in
set_option trace.grind.eqc true in
theorem grind_more_steps : fib 5 = 5 := by grind (ematch := 7) [fib, fib.go]
-- Try lowering to (ematch := 6) -> fails; 7 is the flip point for fib 5.
-- Bump the goal (e.g. fib 8) and you need a correspondingly higher ematch.

/-! ## 4. `grind` diagnostics ON SUCCESS -- opt in with a trace

On success grind is silent by default. Turn on `trace.grind.eqc` to see the
equivalence classes it closed the goal with. Here we hand grind the reduced
fact via `rfl`, so it succeeds; the trace shows it merging `fib 5` with `5`. -/

set_option trace.grind.eqc true in
theorem grind_succeeds : fib 5 = 5 := by
  have h : fib 5 = 5 := rfl   -- rfl does the computation...
  grind                       -- ...grind just closes by congruence

/-! ## 5. `set_option diagnostics true` -- the general counter view

A tactic-agnostic switch: reports unfolding counts, instance-resolution counts,
and (for `decide`) how much the kernel had to reduce -- but only when a counter
crosses a threshold, so trivial goals stay silent. Useful to spot a `decide`
that is secretly doing a huge reduction. Bump the index to make it fire. -/

set_option diagnostics true in
example : fib 20 = 6765 := by decide

/-! ## Quick reference

  #reduce e                              -- normal form (what rfl targets)
  #eval e                                -- compiled evaluation (fast)
  simp only [f, f.go]  + trace.Meta.Tactic.simp.rewrite   -- unfolding steps
  grind                                  -- diagnostics auto-print ON FAILURE
  trace.grind.eqc / trace.grind          -- grind internals ON SUCCESS
  set_option diagnostics true            -- generic counters (unfolds, instances)
  set_option maxRecDepth 1000 in ...     -- if a big #reduce/decide overflows

All are plain `set_option`s -- put `... in` before a decl to scope one to it, or
`set_option X true` on its own line to switch it on for the rest of the file.
-/
