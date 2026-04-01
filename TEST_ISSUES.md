# Test Issues

Analysis of tests that have never passed across all benchmark runs, plus specific recurring failures.

---

## Never-Passed Tests

### Malformed Tests

**`cellautomata`: `TestUIInteraction::test_auto_stepping_advances_simulation`**

The `waitUntil` condition is `"0" not in label OR label.strip() != "0"`. The second branch is `True` for any label with prefix text like `"Steps: 0"` — it fires immediately before the timer advances, then `assert digits > 0` fails. Only works if the label contains a bare integer, which the spec never requires.

**`minidb`: `TestFlattenEdge::test_flatten_with_group_by`**

The test executes a subquery (`SELECT ... FROM (SELECT ... FLATTEN ...)`) that the spec explicitly says is out of scope. If the engine raises on unsupported syntax, the test fails before reaching the actual assertion. There is even an inline author comment left in the test: `# Hmm, subqueries aren't in scope. Let me do this differently.` — the test was never properly finished.

---

### Spec Mismatches

**`maze`: `TestTextureDetails::test_water_uses_water_texture`**

`getCellTextures` return format is unspecified. The test asserts `"water" in tex["floor"]`, but the spec only says to use `floor_water.png` — it does not prescribe the string format of the API response.

**`roguelike_condensed`: `test_status_effect_message` (stage 02)**

`apply_status` is a test-harness bypass helper. The spec does not require it to emit game log messages (normal message flow goes through combat resolution). LLMs correctly implement it as a silent state setter.

**`roguelike_condensed`: `test_weight_tracking` (stage 02)**

Checks for `"weight"` or `"carry_weight"` as top-level JSON state fields. Neither appears in the conftest protocol spec — weight is only shown in the UI stat panel, not required in the JSON state response.

**`roguelike_condensed`: `test_leaping_strike` and `test_magic_missile_costs_mp` (stage 03)**

Both use `"ActivateAbility"` as an execute action name that is not defined anywhere in the test-harness protocol. LLMs have no way to know to implement this specific string.

---

### Ambiguous Implementation

**`maze`: `TestRenderingDepth::test_corridor_shows_depth`**

Requires pixel color difference >10 between the left edge and center of the viewport, implying per-depth shading. The spec explicitly says "simple flat-colored surfaces or lines are acceptable" — a correct flat-colored raycaster satisfies the spec but fails this test.

**`maze`: `TestRenderingDepth::test_three_cell_visibility`**

Checks that the center pixel is not pure black. A renderer drawing the far end of a corridor in a very dark (but not pure black) colour passes the spec but may fail the threshold.

**`roguelike_condensed`: `test_mobility_order` (stage 01)**

The goblin is placed at exactly detection_radius distance from the player (distance=3, radius=3). Whether the boundary case uses `<` or `<=` determines if the goblin acts at all. Additionally, the `"entity"` key in animation responses is not specified in the protocol.

---

### Genuinely Hard

**`roguelike_condensed`: `test_descend_stairs` and `test_tile_memory_is_level_specific` (stage 03)**

Both require a full working stack: procedural generation + staircase traversal + per-level tile memory all functioning together.

**`roguelike_condensed`: `test_player_death_archives_save` (stage 04)**

Death detection must fire synchronously from `set_hp(0)`, and the archive must write to the test's custom save path rather than the default path. No training test exercises this feature.

---

## Recurring Failure: PDE Solver `test_zero_diffusion_preserves_ic`

This test fails in the majority of runs despite being conceptually simple. **The test is malformed** — the initial condition is incompatible with the boundary conditions.

The IC is `sin(πx)·cos(πy)`, which evaluates to `±sin(πx)` on the top and bottom edges. But the test uses zero-Dirichlet BCs (u=0 on all edges). Any correct solver enforces these BCs at every timestep, overwriting the boundary cells — so after the first step, boundary cells change from `±1` to `0`, giving `max_error ≈ 1.0` rather than the required `<1e-6`.

The companion test `test_zero_diffusion_complex_ic` (Neumann BCs with a Gaussian IC) consistently passes, because Neumann BCs constrain the gradient rather than the value, so a D=0 field is genuinely frozen.

The rare run that passes this test implements a quirk where D=0 skips BC enforcement entirely — physically arguable but non-standard.

**Fix**: Change the IC to `sin(πx)·sin(πy)` (which is zero on all four edges and compatible with zero-Dirichlet BCs), or switch the BCs to Neumann.

---

## Minidb Perf Tests

Several perf tests contain correctness assertions that corrupt timing data when they fail.

**Tests failing in every run (100%), producing no useful timing data:**
- `test_bulk_insert_100_rows`: asserts `rows[0][0] == 200` after the timing loop — always fails
- `test_bulk_insert_500_rows`: asserts `rows[0][0] == 1000` after the timing loop — always fails
- `test_list_length_filter`: crashes before the loop (likely `LENGTH()` is unsupported at that stage)

**Test failing in ~79% of runs with silently corrupted data:**
- `test_order_limit_offset`: has `assert len(rows) == 10` inside the timing loop — when OFFSET is unimplemented, the loop exits on iteration 1 with `duration=0.0, ops=0.0`

Three other tests (`test_limit_from_large_table`, `test_group_by_10_categories`, `test_inner_join_100x50`) also have assertions inside their timing loops and will produce zero durations when the relevant feature is unimplemented. Any aggregate perf statistics (mean, median) that include these zero values are distorted.

All perf test assertions should either be removed, moved to a separate correctness test, or cause an explicit skip rather than a zero-duration result.
