# Skills: the step-by-step instructions

The assistant's long instructions live in small files, one folder per skill, in `launchkit_provisioner/skills/<name>/SKILL.md`.
The main prompt keeps only who the assistant is, how it writes, the hard rules and a one-line list of the skills. The assistant loads
the matching skill when it needs it and keeps it for the rest of the chat.

| Skill | Used when | Holds |
|---|---|---|
| `collecting-details` | A new campaign or quick purchase is being described | The 4-5 facts to track, the next question, clarifying conflicts, dates, name ideas |
| `existing-campaigns` | Adding to the London, US or Singapore campaign, or listing campaigns | Open by id or name, ask only for what is missing |
| `plan-and-advice` | Details closed, picks made, or the user changes something before approval | Shopping list, advice, stock and vendors, three choices, other dates, vendor delays |
| `approval-and-orders` | An option is chosen, approval, status, orders, the order pack PDF | The approval step, placing the orders, status, the PDF |
| `quick-answers` | Status board, warehouse stock, audit trail, approval levels, vendor comparison | Which tool to call for each |

## Change a rule
Edit the `SKILL.md` of that skill (the text under the `---` header is what the assistant follows; `description` says when to use it).
Nothing else changes. To add a skill, add a folder with a `SKILL.md` and list it in the main prompt in `agent.py`.

## What stays in code, not in a skill
Approvals, limits, amounts and "no order without approval" are enforced by the code, so a skill can never bypass them.
`tests/test_skills.py` checks that every skill loads, is listed in the prompt and names only real tools.

## Branch
This version is on the branch `claude/skills-version`. The flow is meant to be identical to the long-prompt version.
