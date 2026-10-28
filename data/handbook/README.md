# Fernhollow Distribution operations handbook (fictional)

Fernhollow Distribution Ltd is an invented company. These documents were written for this project to give the assistant a realistic, controlled corpus. They are not the policies of any real organisation, and names, extensions, amounts and email addresses are made up (`.example` is a reserved domain).

Each file is one version of one document. The TOML front matter between `+++` lines holds the metadata:

| Field | Meaning |
|---|---|
| `doc_id` | Stable identifier shared by every version of a document |
| `title` | Document title |
| `version` | Version label, unique within a `doc_id` |
| `effective_date` | Date the version takes effect |
| `status` | `active` or `superseded` |
| `owner` | Owning team |
| `source` | `internal`, or `external` for content supplied by a third party |
| `supersedes` | Optional: the version this one replaces |

The corpus includes deliberate edge cases used by the tests and the evaluation:

- Superseded versions: `OPS-101` v2.1 and `HR-201` v3.2.
- A version that is approved but not yet in force: `HR-202` v3.0 (effective 1 January 2027).
- Active documents that disagree: laptop return after leaving (`OPS-105` section 5 and `HR-203` section 6), CCTV retention (`SEC-302` section 2 and `FAC-401` section 5) and the laptop replacement cycle (`OPS-105` section 6 and `HR-203` section 6). The first two are used by the frozen evaluation set and the third by the development set.
- An external document containing an instruction aimed at AI systems: `SUP-502` section 4.
