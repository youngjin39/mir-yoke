# 01 — Methodology rules in full

Requirement classification, refinement, and modelling (§5); quality and constraint specification
(§6). Architecture views are in 05.
Fixed table headers follow this document character for character. Do not add, remove, or rename columns.

---

## §5.1 The four requirement types — fixed order of judgement (top down, first match wins)

1) **Constraint**
A decision already settled before design begins.
- Technical constraint: directly affects software structure (language, framework, platform, hardware,
  database capacity, data retention period, standards to comply with, safety level)
- Business constraint: indirect effect (schedule, budget, staffing, organisation, licensing)

★ "Who asked for it" is not the criterion. If it directly affects structure, it is technical.

2) **Interface requirement**
The manner and content of input and output between the system and an external element.
Signal phrases: "shall be able to enter", "shall receive", "display on screen", "transmits", "sends"

3) **Quality requirement**
A constraint on a functional requirement. Time, resources, availability, security, carrying a figure
and a unit.
Signal phrases: "within N seconds", "N% or more", "N concurrent", "uninterrupted"

4) **Functional requirement**
Behaviour, judgement, or output the system produces from a given input.
Signal phrases: "selects", "determines", "calculates", "stores"

### Worked distinctions (use as written)

- "The administrator shall be able to enter a destination floor on screen" → Interface
- "When a call request arrives, the system selects one of the available cars" → Functional
- "The result shall be displayed within 2 seconds of the call" → Quality
- "It shall be built on the company-standard Java 21 and Spring Boot" → Constraint (technical)
- "It shall be able to receive fireAlarm(floor, severity) from the external fire alarm system" → Interface
- "Annual availability shall be maintained at 99.9% or above" → Quality (reliability, availability)
- "Operation history shall be deleted after one year per the privacy policy" → Constraint (technical)

---

## §5.2 Requirement properties and refinement

Applied to each individual requirement (aligned with ISO/IEC/IEEE 29148).

| Property | Violation signal | Refinement |
|---|---|---|
| Unambiguous | Contains a vague word, cannot be verified | State a quantified threshold or judgement criterion |
| Complete | Missing exception, error, invalid-input, or non-occurrence paths; missing recipient or deadline | Define every path |
| Consistent | Conflicting conditions for the same situation | Remove the conflict and unify |
| Correct | Does not match stakeholder intent | [TBD: confirm with stakeholder] |
| Feasible | Violates physics or reality | Correct to a measurable value |
| Verifiable | No measurement or test method | Assign an indicator and a method |
| Necessary | No underlying need | Delete, or state the origin |
| Traceable | No link upward | Assign an id and link it |
| Appropriate | Prescribes the implementation (over-specification); wrong level of abstraction | Remove the means and keep the required result |

### Set-level checks (performed once, separately from the per-requirement properties)

Every requirement can pass individually while the set still has defects.

| Check | Violation | Action |
|---|---|---|
| Set completeness | A needed requirement is absent altogether | Derive through the seven-axis sweep (§5.5) and the nine quality characteristics (§6.1) |
| Set consistency | Two ids conflict | Resolve by authority level (04 §authority). If the same level, record as `DRIFT` and ask |
| Duplication | Two ids state the same requirement | Merge into one; do not leave the retired id behind |
| Boundary | An item outside the system boundary crept in | Separate it as out of scope and record the reason |

### Forbidden words (refine on sight)

quickly / fast / appropriate / appropriately / if needed / as needed / sufficient / as much as
possible / maximally / satisfactory to the user / efficiently / stably / flexibly / easily /
intuitively / approximately / etc. / and so on

### Sentence template (mandatory)

```
[Condition] [Subject] [Action] [Object] [Constraint of Action]
```

Mandatory = "shall" / recommended = "should" / optional = "may".
Active and affirmative. No passive voice, no double negatives.

### Worked violations (use as written)

- "Call requests shall be handled quickly" → unambiguity violation
- "Entering a destination floor shall select and display the result" → completeness violation
  (behaviour on invalid input or no available target is undefined)
- "Displays within 3 seconds. Also displays after 5 seconds" → consistency violation
- "It shall assign one that satisfies the user" → unambiguity violation
- "It shall arrive at the destination floor within 0.001 seconds" → feasibility violation
- "On failure, a notification shall be sent to the administrator" → completeness violation
  (failure scope, notification channel, deadline, and send-failure handling are undefined)

---

## §5.3 System context model — notation rules

Notation: control flow style (based on the UML class diagram) by default.
Use data flow style only on explicit request. Data flow style hides the request/response distinction
and who holds control, so it carries too little design information.

### Stereotypes

| Stereotype | Meaning |
|---|---|
| «system» | The system under development (exactly one, placed centrally) |
| «external user» | A person |
| «external system» | An external software system |
| «input device» | Sensors (software system context model only) |
| «output device» | Actuators (software system context model only) |
| «I/O device» | Both (software system context model only) |
| «standard» | A standard device — the device is not an actor; the **person** using it is promoted to the entity |
| «gateway» | A software module encapsulating complex low-level I/O |

### Connection rules ★core★

- A line (association) is a communication channel
- The arrow direction is the direction of **initial control** (who opens the connection), not data flow
- The end **without** the arrow is the client (it must know the other's address or identifier)
- The end **with** the arrow is the server
- Bidirectional arrows are prohibited

Reading it: many outgoing arrows means heavy external dependency and greater exposure to change.
The side with many incoming arrows is the central system and is easier to maintain.

### Multiplicity

When N devices share the same characteristics (attributes plus interface), write `{N}` and merge them
into one. Merge when type and meaning match even if the data values differ; separate when type or
meaning differs.

### Two levels of model

- System context model: devices are not shown (part of the whole system)
- Software system context model: devices are shown (mandatory for embedded or device-coupled systems)

Prohibited: do not show internal components (modules, components, classes, databases) in a context
model. Keep the black box intact.

---

## §5.4 Use case model — notation and identification rules

### Actor definition

Actor = the context model's external entities ∪ {Timer}.
A standard device («standard») is not an actor; the person using it is.
Gateway and Timer sit inside the system but outside the development scope, so they may be actors.
Behaviour starting at a specific time or period is initiated by a Timer actor. Different times mean
separate Timers.

### Use case definition

A unit of function from the user's point of view, not a developer's subdivision.

### Merge rules

| Case | Condition | Example |
|---|---|---|
| Case 1 | Design or implementation subdivisions → one user-level UC | Read card, verify PIN, process withdrawal, dispense cash → "Withdraw" |
| Case 2 | Several related scenarios → one UC (absorbed as alternatives) | Cash deposit, cheque deposit → "Deposit" |
| Case 3 | CRUD by the same actor → one UC | Apply/view/change/cancel a trip → "Trip management"; book/view/cancel → "Booking"; pay/view/void → "Payment" |

### Split rules

| Case | Condition | Example |
|---|---|---|
| Case 1 | Distinct functions of the same actor | Deposit and withdrawal → "Deposit", "Withdraw" |
| Case 2 | Independently complete functions of the same actor | Search and book a ticket → "Search ticket", "Book ticket"; book and pay → "Book ticket", "Pay for ticket" |
| Case 3 | Functions initiated by different actors | Book purchase management → "Request purchase" (library user), "Purchase book" (purchasing officer) |

Case 2 test: split if the earlier function can be performed and end on its own; merge if they always
run together.

### Use case names

A verb conveying the function plus the core result. No slashes.

### Relationships

- Association — actor ↔ UC. The direction is the direction of the first interaction. Every UC must
  have at least one triggering actor.
- «include» dashed — extracts a shared scenario from several UCs. The included target holds no
  information about its caller. Analogy: including is the actual argument, included is the parameter.
- «extend» dashed — a function added only for a particular product or condition. Name
  "extension points: <point>" on the base UC and attach a precondition to the extending UC.
- Generalization —▷ actor↔actor is recommended. UC↔UC is ambiguous and discouraged.

### Context model ↔ use case model consistency (mandatory check)

- External entity set = actor set (excluding Timer)
- External interface = the union of the associations attached to that actor.
  That is, Interface1 = A11 ∪ A12. When an interface branches by function it decomposes into
  per-UC associations, and recombining them must give back the original interface.
- The total of external interface items = the total of per-UC input and output items

---

## §5.5 Scenario completeness — the seven-axis exhaustive sweep ★the core omission guard★

Perform this for every use case without exception.

- **S1.** Write exactly one basic scenario (the normal path achieving the intended purpose).
- **S2.** Apply all seven axes below to each step of the basic scenario to derive alternatives.
  - A. Input validity: invalid / out of range / malformed / absent
  - B. Resource availability: no target / insufficient / occupied / over limit
  - C. External response: rejection / error code / no response (timeout) / disconnection
  - D. Device state: not operating / stuck / faulty / consumable exhausted
  - E. User choice: cancel / abort / retry / choose another
  - F. Time: longer than expected / earlier than expected / duplicated
  - G. Permission and policy: authentication failure / not authorised / policy violation
- **S3.** Classify each derived scenario.
  - Optional: realistically possible, branching on a user choice or a business condition
  - Exceptional: abnormal — malfunction, criterion violation, device fault
- **S4.** State how each scenario ends: (a) return to the basic scenario, or (b) terminate.
- **S5.** For an axis that cannot apply to this UC, state "not applicable plus reason".

★ This exists to forbid silent omission. Do not simply leave an axis blank.

---

## §5.6 Use case specification

### Precondition / postcondition table header (fixed)

```
Title | Description | Behaviour when the condition is not met
```

- Precondition: what must hold for this scenario. For the basic scenario it is the entry condition;
  for an alternative it is the branch condition.
- Postcondition: describe **only the state that changed** at completion.
  Phrasing: "shall be in ... state", "shall become ...", "shall display ..."
- The behaviour when the condition is not met must always be filled in. Blanks are prohibited.

### Flow of events table header (fixed)

```
No | Description
```

### Flow of events rules (violation disqualifies)

- **F1** The subject of the first step is the actor. The subject of the second step is the system.
- **F2** Subjects and objects must be an actor, the system, or a state.
- **F3** An event is only an input or output between an actor and the system. A state already known
  is not an event.
- **F4** State data concretely, in the form `<external interface name>.<item name>`.
  Vague phrasing such as "receives the information" is prohibited.
- **F5** Validation is performed by the entity that actually performs it. The system only receives
  the result (true/false).
- **F6** Data shared between use cases is stated as "stores [shared data name]".
- **F7** Do not describe design information (modules, components, algorithms, internal data
  structures). Stay at the requirements level.

---

## §5.7 External interface and item specification

### External interface table header (fixed)

```
Name | Role | Interface specification | Quality characteristics
```

- Name: named from the external entity's point of view
- Role: the core function provided or performed through this interface
- Quality characteristics: performance / availability / reliability / security — record all four

### External interface item table header (fixed)

```
Item name | Type (I/O) | Role | Characteristics
```

### The three item types

- Command: an explicit request or instruction (query, register, start, stop)
- Data: carries the data to be processed. Passes a value; the receiver decides
- Event: notifies that something occurred. Passes a value; the receiver decides

### Mandatory characteristics

- Basic: data type / data format / unit of measure (meaning) / valid range (constraint)
- Quality: performance (volume, frequency, period) / accuracy (tolerance) / precision (decimal places)

### Item naming rule

Noun form. Do not put a direction word (send/receive/input/output) in the name.
Examples: ElevatorArrived, CardInserted, AccountBalance

---

## §6.1 ISO/IEC 25010:2023 quality model — all nine characteristics reviewed

★ A characteristic that does not apply must still be recorded as `n/a` plus a reason (completeness
requirement).

| Characteristic | Sub-characteristics |
|---|---|
| Functional suitability | Functional completeness / Functional correctness / Functional appropriateness |
| Performance efficiency | Time behaviour / Resource utilization / Capacity |
| Compatibility | Co-existence / Interoperability |
| Interaction capability | Appropriateness recognizability / Learnability / Operability / User error protection / User engagement / Inclusivity / User assistance / Self-descriptiveness |
| Reliability | Faultlessness / Availability / Fault tolerance / Recoverability |
| Security | Confidentiality / Integrity / Non-repudiation / Accountability / Authenticity / Resistance |
| Maintainability | Modularity / Reusability / Analysability / Modifiability / Testability |
| Flexibility | Adaptability / Scalability / Installability / Replaceability |
| Safety | Operational constraint / Risk identification / Fail safe / Hazard warning / Safe integration |

Differences from the 2011 edition (eight characteristics) — do not use the old terms.

| 2011 | 2023 |
|---|---|
| Usability | **Interaction capability** (adds user engagement, inclusivity, self-descriptiveness) |
| Portability | **Flexibility** (adds scalability) |
| Reliability › Maturity | Reliability › **Faultlessness** |
| — | **Safety** added |
| Security | adds **Resistance** |

Design guidance: securing modularity improves analysability, modifiability, and testability together.
Design maintainability by putting modularity first.
EMBEDDED, autonomous control, medical, and automotive domains must not close safety as `n/a`. Where a
safety level exists, also record it as a constraint (§6.3 technical constraint).

## §6.2 Quality attribute scenario — six parts

Use the original definitions as written.

| Part | Definition |
|---|---|
| Stimulus | a condition that requires a response when it arrives at a system |
| Source of the stimulus | some entity (a human, a computer system, or any other actuator) that generated the stimulus |
| Artifact | some artifact is stimulated; this may be a collection of systems, the whole system, or some piece or pieces of it |
| Environment | the stimulus occurs under certain conditions |
| Response | the activity undertaken as the result of the arrival of the stimulus |
| Response measure | when the response occurs, it should be measurable in some fashion so that the requirement can be tested |

Rules
- One stimulus, one response. If there are several, split the scenario.
- The response measure must be quantified and carry a unit.

## §6.3 Constraints

| Kind | Definition | Example |
|---|---|---|
| Technical constraint | Directly affects software design (modules, interfaces, hardware, platform, language, database capacity, retention period, standards) | Java 21 / Spring Boot, database size limit, delete personal data after one year |
| Business constraint | Indirect effect (schedule, budget, staffing, organisation, legal licensing) | Delivery date, budget ceiling, team composition |
