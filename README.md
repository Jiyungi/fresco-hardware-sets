# Door Hardware Set Extractor

**Demo video (4:44):** https://www.loom.com/share/63f6678cdc394eb9b0afe497a7a21337

## What it does

A construction spec book is a long PDF describing everything in a building. Somewhere inside is a list of
**hardware sets**: for each kind of door, the parts it needs (hinges, locks, closers...). This program finds every
set in the PDF and writes it out as a clean table.

Example: page 643 of the Livelle book (folder "Livelle Mulholland - Life Plan Community", file
`2025-12-12_Livelle_Bid_Set_Project_Manual_Vol1_rev1.pdf`) prints:

```
Set: 1.0
Description: Unit Entry Door (WDL)
3   Hinge, Full Mortise          TA2714        US15   MK
1   Surface Closer Cush Stop     CA1601 P      689    NO
1   Sound Gasketing              S773BL                PE
```

and the program writes:

| Set | Name | Page | How many | What | Model number | Finish | Maker |
|---|---|---|---|---|---|---|---|
| 1.0 | Unit Entry Door (WDL) | 643 | 3 | Hinge, Full Mortise | TA2714 | US15 | MK |
| | | | 1 | Surface Closer Cush Stop | CA1601 P | 689 | NO |
| | | | 1 | Sound Gasketing | S773BL | *(blank)* | PE |

It also records exactly where each set and each part sits on the page, and a "how sure" score for every value.

**No AI model is used when it runs.** It is a set of fixed rules written in Python, so it is fast, free and gives
the same answer every time. (AI was used to help write the code and to make answer sheets for testing.)

## Try it

Needs Python 3.10 or newer. Put the spec book PDFs in this folder, in their project sub-folders as delivered.

```bash
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python -m hardware_sets .            # read every PDF under this folder (about 2.5 minutes for all 43)
streamlit run review_app.py          # the review screen
pytest                               # the 62 automatic tests
```

Results go to `output/<project folder>/<file name>.json` (full detail) and `.csv` (one row per part; opens in Excel).
To read one book: `python -m hardware_sets "HFH DG - HOSPITAL/08 71 00 - DOOR HARDWARE.pdf"`.

## How it works

| Step | What it does | File |
|---|---|---|
| 1. Read the words | A PDF stores every word and its position on the page. The program reads them and groups words at the same height into lines. It drops crossed-out words (deleted by a revision), sideways margin text and small icons. | [`pdf_text.py`](hardware_sets/pdf_text.py) |
| 2. Find the set pages | Keeps pages that have a set title ("Set: 1.0", "Hardware Group No. 01", ...) and lines that look like parts. In the Livelle book, 1,191 pages come down to 58. | [`page_finder.py`](hardware_sets/page_finder.py) |
| 3. Remove page headers and footers | Text repeated at the top or bottom of every page is dropped, so a set that runs onto the next page reads as one list. | [`furniture.py`](hardware_sets/furniture.py) |
| 4. Find the columns | Uses the table's header row when there is one ("QTY DESCRIPTION CATALOG NUMBER FINISH MFR"). Otherwise it counts where text keeps starting on each line: in Livelle, at 88, 263, 442 and 491 points from the left edge, so four columns. | [`columns.py`](hardware_sets/columns.py) |
| 5. Tell makers from finishes | Checks every value in a column against lists of known maker codes and known finish codes. The column with mostly makers is the maker column. So "PE", which can mean Pemko (maker) or painted enamel (finish), is read by the column it sits in. | [`columns.py`](hardware_sets/columns.py), [`codes.json`](hardware_sets/data/codes.json) |
| 6. Sort the lines | A title starts a new set. A line starting with a number starts a new part. A line with no number continues the part above it. "Notes:" goes to the set's notes. | [`parser.py`](hardware_sets/parser.py) |
| 7. Fill in the boxes | Each word goes into the box of the column it sits under, and each value gets a "how sure" score. | [`assemble.py`](hardware_sets/assemble.py), [`confidence.py`](hardware_sets/confidence.py) |
| 8. Save | One results file per PDF, plus a spreadsheet. | [`output.py`](hardware_sets/output.py) |

[`extract.py`](hardware_sets/extract.py) runs these steps in order for one PDF.

## How well it works

All 43 PDFs (21 projects): **1,307 sets and 11,519 parts** found in about 2.5 minutes. The 22 files that contain no
hardware sets (glass, wood doors, mirrors, ...) correctly return nothing.

No answer sheet came with the challenge, so we made our own (see [How we checked](#how-we-checked)). The fair tests
use sets the program was **never tuned on**, scored **once**, on a saved copy of the program, before any fixes:

| Test | Sets | Parts exactly right | Whole sets exactly right | Maker | Finish |
|---|---|---|---|---|---|
| Held-out sets | 22 sets, 13 books | 192 / 197 (97.5%) | 16 / 22 (73%) | 98.0% | 98.0% |
| Fresh sets | 43 sets, 18 books | 358 / 372 (96.2%) | 35 / 43 (81%) | 98.1% | 97.8% |
| **New sets (latest)** | 39 sets, 17 books | **330 / 332 (99.4%)** | **37 / 39 (95%)** | 99.7% | 99.7% |

"Exactly right" means how many, what it is, model number, maker and finish all match (ignoring capital letters and
spaces). A whole set is right only if every part in it is right and none is missing or extra.

- **Improving across rounds:** each test round found mistakes, which were then fixed, and the next round used new sets. The latest round, on the most recent version of the program, is the best measure.
- **After fixing what each round found:** the program now scores 197/197, 370/372 and 332/332 on those sets. These numbers are no longer independent. The 2 remaining differences are judgment calls: whether an unlabelled line like "Shared with D14B" is a note or part of the name.
- **Found outside the tests:** while preparing the demo, Livelle set 45.0 showed a model number split between two parts. It was printed half a line above and half a line below its own row, and the top half went to the part above. The same layout (also in the finish column, "Dark" / "Bronze") affected 82 parts in 39 sets (Livelle and JC Ryan). It is fixed, and no answer-sheet score changed, because no answer sheet happened to include that layout. The answer sheets sample the books; they don't cover every set.
- **Finding the sets:** every set title was found in all 20 books that have sets (1,182 titles, none invented).
- **Reports:** [`eval/report_new_frozen.md`](eval/report_new_frozen.md), [`eval/report_fresh_frozen.md`](eval/report_fresh_frozen.md), [`eval/report_holdout_frozen.md`](eval/report_holdout_frozen.md).

## How we checked

**The answer sheets.** The correct answer is simply what is printed on the page, so an answer sheet is a careful copy
of it. Separate AI helper sessions made the copies (not a person); they could not see the program or its results.
Rules for copying: [`eval/transcription_rules.md`](eval/transcription_rules.md).

**Checking the answer sheets:**
- **Two independent copies:** the held-out sets, the new sets and the development sets were each copied twice, by different helpers, and the copies were compared. (The 43 fresh sets were copied once; their differences from the program were checked on the page images.)
  - They agreed on 99.7-99.8% of values.
  - Every disagreement was about how to apply a rule, not about misreading the page.
  - Each disagreement was decided using the page image and logged in [`eval/key_corrections.md`](eval/key_corrections.md).
- **Every value is on its page:** [`eval/check_key.py`](eval/check_key.py) confirms each value in the answer sheets appears on its page.
- **Honest limit:** AI copiers could all misread something the same way. A person checking a few sets in the review screen is still the strongest proof.

**Checks that need no answer sheet**, using only the PDFs themselves:

| Check | Result |
|---|---|
| **Nothing invented**: every value the program wrote appears on its page ([`check_output.py`](eval/check_output.py)) | 42,201 of 42,211. The other 10 are long cells whose words the PDF stores out of order; each was checked on the page. |
| **Nothing missed**: the hospital's own door list names the set each door uses | All 63 set numbers found |
| **Locations**: each set's number sits inside its box, and each part sits inside its set's box with its own text inside its box ([`check_locations.py`](eval/check_locations.py)) | All 1,307 sets and 11,519 parts |
| **Odd results**: a finish in the maker box, a row with no text, a huge quantity ([`audit.py`](eval/audit.py)) | Found 6 real bugs, all fixed. Every remaining flag is correct as printed; e.g. "857 latchsets" is real, because that set covers 857 closet doors. |
| **Same sets, two files**: Gerrard and Bridgeport each have the same sets in two PDFs | Identical results |

**62 automatic tests** ([`tests/`](tests)), each built from a real case in these PDFs, rerun in seconds after every change.

## "How sure" scores

The guide asks for "confidence scores on extracted fields" without defining them. Here, each value gets a score from
0 to 1 made of four simple checks ([`confidence.py`](hardware_sets/confidence.py)):
1. Does the value start where its column starts?
2. Does it look like what belongs in that column (a maker code in the maker column, and so on)?
3. Was the row a plain single line, or pieced together from split lines?
4. How clearly did the maker-vs-finish vote go?

Values below 0.7 are marked "needs checking" (orange in the review screen, listed in the spreadsheet).

- **First version failed its test:** on the fresh sets it flagged none of the program's 23 mistakes. It was redesigned; the redesigned score flags 1.7% of values and catches 16 of those 23.
- **Newest test:** on the 39 new sets the saved program got 1 value wrong and missed 1 row. The score did not flag the wrong value, a remark that belonged in notes. With so few mistakes, this test can't show whether the score works. Reports: [`eval/report_confidence_new_score_frozen_program.txt`](eval/report_confidence_new_score_frozen_program.txt), [`eval/report_confidence_new_sets_frozen.txt`](eval/report_confidence_new_sets_frozen.txt).

## Review screen

`streamlit run review_app.py`:
- **Left:** the PDF page. A red box marks the chosen set, blue boxes its parts, orange boxes parts to check, and grey boxes other sets on the same page.
- **Right:** the set's number, name and parts in an editable table.
- **"Only sets that need checking":** shows just the sets with something to check.
- **Save corrections:** writes the fixed set to `corrections/`, in the same format as the answer sheets, so every fix also becomes test data.
- **Upload:** you can also upload a new PDF and read it.

## What the output contains

The guide's four fields:

| Field | Meaning |
|---|---|
| `set_number` | As printed, without label words: "001", "3A", "EX-1.0", "AL 01". |
| `description` | The set's name, from its title line or a "Description:" line. Empty when the book prints none. |
| `location` | The page number and a box on that page. The box is `[left, top, right, bottom]` in points (1/72 inch) from the page's top-left corner. A set on two pages gets one box per page, and each part has its own box. |
| `components` | Each part: `qty` (empty when not printed, never guessed), `description`, `catalog_number`, `mfr`, `finish`, `notes`. |

Extras:

| Extra | What it's for |
|---|---|
| `unit` | EA, SET, PR |
| `not_used` | Sets marked "Not Used" or "moved to another set" are kept and marked |
| `doors` | Door numbers listed with the set |
| `mfr_name`, `finish_name` | Full names, e.g. IVE = Ives, when the PDF or the code list defines them |
| `catalog_codes` | Option codes explained by the PDF's own list, e.g. NRP = Non-Removable Pins |
| `electrified` | From the "electrified" icon some books print |
| `confidence` | The "how sure" scores |
| `set_notes`, `warnings` | Notes for the whole set, and anything that needs a look |

## The guide's tricky cases

| Case | Example | What the program does |
|---|---|---|
| Same code, two meanings | "PE" (Pemko or painted enamel), "NO" (Norton or the word "No.") | Decided by the column it sits in, never by the letters alone |
| Unclear set boundaries | About 12 title styles; Roselle has no titles, only a grid with a SET column | Title patterns, plus "a new number in the SET column starts a new set" |
| "Not Used" sets | Lyons "Hardware Group No. 05 - Not Used", SJC "Moved to Exterior Set HW E18" | Kept and marked `not_used` |
| Sets over two pages | Most hospital sets | Page headers/footers removed; one list, one box per page |
| Different layouts | No maker column (Bridgeport), maker inside the product text (Roselle), each set with its own column positions (Commons Lane) | Columns read per book, per section, and per set when needed |
| Missing quantities | "--", "__", "*", "As Req." | Left empty |
| Crossed-out text | Hospital revision bulletins, SJC, Valor | Left out |

## Limits

- **New layouts:** a book laid out in a new way may need a new rule. The review screen and the "how sure" scores are there to catch those cases.
- **Scanned PDFs:** pages that are only pictures are not read. All hardware pages in these 43 files contain real text.
- **Judgment calls:** whether an unlabelled remark belongs to a part or to the whole set is sometimes debatable, so notes are not counted in "exactly right".
- **Short-code bonus:** codes are turned into full names only when the PDF prints a code list (National, Forest Park) or the code is in [`codes.json`](hardware_sets/data/codes.json). None of these PDFs uses codes like "A" that stand for a whole part, so that case was not built.

## Files

```
hardware_sets/        the program (steps above)
  data/codes.json     known maker and finish codes (editable)
review_app.py         the review screen
output/               results for the 43 PDFs
eval/                 answer sheets, scoring and check scripts, reports
tests/                62 automatic tests
```
