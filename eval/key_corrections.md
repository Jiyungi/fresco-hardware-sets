# Corrections made to the answer keys

Every set in `eval/answer_key` and `eval/holdout_key` was copied a second time, independently, into `eval/second_copy` and `eval/second_copy_holdout` (same rules: `eval/transcription_rules.md`). The two copies agreed on 3,767 of 3,777 values. The 10 disagreements were all about applying the rules, not about reading the page; each was decided by the rules and the page image, giving these corrections:

- `eval/answer_key/morris.json`: SFIC notes in sets 101, 103, 106.38: keep the second bullet's "- " ("... selections - End user ..."); rule 9 only drops the leading "- " of a note.
- `eval/holdout_key/morris_holdout.json`: set CR38: drop the leading "- " of two notes (rule 9).
- `eval/answer_key/valor.json`: set 05 description without the door numbers ("Mechanical Closet Swing Doors"); set 12 description null, its title holds only door numbers (rule 3).

A spacing-only difference ("( NIGHT" vs "(NIGHT") is now ignored by the scoring (spaces next to brackets and commas do not count).

## New random sets (round 4)

39 new sets were copied twice, independently (`eval/new_key_a`, `eval/new_key_b`). The copies agreed on 2,398 of
2,402 values. The one disagreement: Bridgeport set 19 prints "*Confirm Door Thickness" on its own line under two
catalog numbers. Rule 9 sends only bracketed remark lines to notes, so by the rules it is part of the catalog
number, as in copy A. The final key `eval/new_key` is copy A.
