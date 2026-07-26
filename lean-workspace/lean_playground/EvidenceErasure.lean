/-!
Evidence erasure: `Exists` (Prop) vs `Sigma`/`Subtype` (Type).

This file makes the truncation boundary concrete. Same mathematical content --
"there is a natural number greater than zero" -- expressed three ways:

  * `{n // n > 0}`  (Subtype, lives in `Type`)  -- witness is DATA, projectable
  * `Σ' n, n > 0`   (PSigma,  lives in `Type`)  -- witness is DATA, projectable
  * `∃ n, n > 0`    (Exists,  lives in `Prop`)  -- witness ERASED, not projectable

(We use `Σ'`/`PSigma` rather than `Σ`/`Sigma` because core `Sigma` requires its
second component to be a `Type`, whereas `n > 0` is a `Prop`. `PSigma` allows
either -- and, being in `Type`, still lets you project the witness.)

The HoTT analogy: `∃` is the propositionally-TRUNCATED existential `‖ Σ ‖`.
Lean's `Prop` is the universe of "mere propositions" -- but forced: definitional
proof irrelevance means every `Prop` is automatically an h-prop.

Open in the browser IDE and put your cursor on each `#eval` / `#check` line to
watch the InfoView. Everything here compiles: the deliberately-illegal
extraction is wrapped in `#check_failure`, which SUCCEEDS precisely because the
term inside it fails to elaborate.
-/

/-! ## 1. The `Type` world: witnesses are data you can compute with -/

-- A Subtype value: the number 5 packaged with a proof that 5 > 0.
def subWitness : {n : Nat // n > 0} := ⟨5, by decide⟩

-- `.val` projects the witness back out as an honest `Nat`. Cursor here -> 5
#eval subWitness.val

-- ...and you can compute with it like any other Nat. Cursor here -> 10
def doubleIt (s : {n : Nat // n > 0}) : Nat := s.val * 2
#eval doubleIt subWitness

-- Same story with a PSigma type. `.1` is the witness, `.2` is its proof.
def sigWitness : Σ' n : Nat, n > 0 := ⟨5, by decide⟩
#eval sigWitness.1   -- 5

/-! ## 2. Proof irrelevance: the PROOF half is already erased, even in `Type`

Two Subtype values with the SAME witness but DIFFERENT-looking proofs are
definitionally equal -- `rfl` closes it. The `> 0` proofs `h1` and `h2` are
proofs of a `Prop`, so their identity is irrelevant. This is UIP/Axiom K in
action, and it is exactly what HoTT gives up to keep univalence. -/

example (h1 h2 : (5 : Nat) > 0) :
    (⟨5, h1⟩ : {n : Nat // n > 0}) = ⟨5, h2⟩ := rfl

/-! ## 3. The `Prop` world: `Exists` erases the witness

`∃ n, n > 0` asserts THAT a witness exists without retaining WHICH one. You
cannot pattern-match it back into `Type` (a `Nat`). The recursor `Exists.rec`
may only eliminate into `Prop`, so trying to build data from it is rejected.

`#check_failure e` type-checks iff `e` fails to elaborate -- so the fact that
THIS FILE COMPILES is the proof that the extraction below is genuinely illegal. -/

theorem existsWitness : ∃ n : Nat, n > 0 := ⟨5, by decide⟩

-- Illegal: match an `∃` (Prop) to produce a `Nat` (Type). Elaboration fails,
-- so `#check_failure` succeeds. Uncomment the `def` below to see the real error
-- ("motive is not type correct" / elimination-into-Type restriction).
#check_failure (fun (h : ∃ n : Nat, n > 0) => match h with | ⟨w, _⟩ => w)

-- def extractBad (h : ∃ n : Nat, n > 0) : Nat :=
--   match h with
--   | ⟨w, _⟩ => w

/-! ## 4. The escape hatch: `Classical.choose` -- witness back, but noncomputable

You CAN recover a witness from an `∃`, but only via the axiom of choice, which
makes the definition `noncomputable`: it has no runtime behaviour, so `#eval`
refuses it. That is Lean telling you the evidence was truly gone at the
computational level -- choice conjures a witness logically, not by running code.

Contrast with section 1, where `subWitness.val` needed no axiom and `#eval`s fine. -/

noncomputable def extractWitness (h : ∃ n : Nat, n > 0) : Nat :=
  Classical.choose h

-- The recovered witness still satisfies the predicate (this is a Prop, so fine).
theorem extractWitness_pos (h : ∃ n : Nat, n > 0) : extractWitness h > 0 :=
  Classical.choose_spec h

-- `#eval extractWitness existsWitness`  -- would error: noncomputable, no code.

-- The `Type`-world extraction, by contrast, is axiom-free:
#print axioms doubleIt          -- 'doubleIt' does not depend on any axioms
#print axioms extractWitness    -- depends on axioms: [Classical.choice]
