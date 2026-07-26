/-!
InfoView demo.

Open this file in the browser IDE and open the Lean InfoView (the ∀ button in
the top-right of the editor toolbar). Then click on the lines noted below and
watch the InfoView panel on the right update.

The Lean server takes ~30-60s to start the first time (bottom status bar shows
its progress); the InfoView stays quiet until it's ready.
-/

-- 1. Put your cursor anywhere on the next line.
--    The InfoView's "All Messages" section shows:  Nat
#check Nat

-- 2. Cursor on this line -> "All Messages" shows the evaluated value:  120
#eval (1 * 2 * 3 * 4 * 5)

-- 3. Cursor on this line -> shows the type of Nat addition:  Nat -> Nat -> Nat
#check (Nat.add)

-- 4. An interactive proof. Click right AFTER the word `by` on the line below
--    (before `rfl`). The InfoView "Tactic state" shows the remaining goal:
--        ⊢ 2 + 2 = 4
--    Then click after `rfl` and the goal disappears -> "No goals".
example : 2 + 2 = 4 := by rfl

-- 5. A deliberately unfinished proof: cursor after `by` shows the open goal
--        ⊢ n + 0 = n
--    and there is a red squiggle because the proof is incomplete (sorry).
example (n : Nat) : n + 0 = n := by
  sorry
