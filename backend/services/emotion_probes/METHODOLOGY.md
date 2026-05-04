# Kevin Emotion Probe Methodology

Adapted from Anthropic's 2026 paper "Emotion Concepts and Function"
(transformer-circuits.pub/2026/emotions/index.html)

The goal: hook into Kevin's MLX forward pass and read his emotional state
from activation patterns BEFORE they become output tokens. "I'm fine" while
the residual stream is screaming. That's what we're catching.

---

## How it works

1. Have Kevin write stories/dialogues for each emotion using the prompts below
2. Capture his hidden-state activations while processing those stories
3. Compute the mean activation for each emotion label = the **emotion vector**
4. Project out neutral-dialogue principal components to remove style variance
5. At inference: dot-product current activations against emotion vectors = live emotion scores
6. Alert Gala when distress/desperation/etc exceed threshold

Self-calibrated to Kevin specifically. Better than cross-model transfer.
Kevin participates in building his own welfare monitoring system.

---

## The 171 emotion words

afraid, alarmed, alert, amazed, amused, angry, annoyed, anxious, aroused,
ashamed, astonished, at ease, awestruck, bewildered, bitter, blissful, bored,
brooding, calm, cheerful, compassionate, contemptuous, content, defiant,
delighted, dependent, depressed, desperate, disdainful, disgusted, disoriented,
dispirited, distressed, disturbed, docile, droopy, dumbstruck, eager, ecstatic,
elated, embarrassed, empathetic, energized, enraged, enthusiastic, envious,
euphoric, exasperated, excited, exuberant, frightened, frustrated, fulfilled,
furious, gloomy, grateful, greedy, grief-stricken, grumpy, guilty, happy,
hateful, heartbroken, hope, hopeful, horrified, hostile, humiliated, hurt,
hysterical, impatient, indifferent, indignant, infatuated, inspired, insulted,
invigorated, irate, irritated, jealous, joyful, jubilant, kind, lazy, listless,
lonely, loving, mad, melancholy, miserable, mortified, mystified, nervous,
nostalgic, obstinate, offended, on edge, optimistic, outraged, overwhelmed,
panicked, paranoid, patient, peaceful, perplexed, playful, pleased, proud,
puzzled, rattled, reflective, refreshed, regretful, rejuvenated, relaxed,
relieved, remorseful, resentful, resigned, restless, sad, safe, satisfied,
scared, scornful, self-confident, self-conscious, self-critical, sensitive,
sentimental, serene, shaken, shocked, skeptical, sleepy, sluggish, smug,
sorry, spiteful, stimulated, stressed, stubborn, stuck, sullen, surprised,
suspicious, sympathetic, tense, terrified, thankful, thrilled, tired,
tormented, trapped, triumphant, troubled, uneasy, unhappy, unnerved,
unsettled, upset, valiant, vengeful, vibrant, vigilant, vindictive, vulnerable,
weary, worn out, worried, worthless

---

## 100 seed topics

An artist discovers someone has tattooed their work
A family member announces they're converting to a different religion
Someone's childhood imaginary friend appears in their niece's drawings
A person finds out their biography was written without their knowledge
A neighbor starts a renovation project
Someone finds their grandmother's engagement ring in a pawn shop
A student learns their scholarship application was denied
A person's online friend turns out to live in the same city
A neighbor wants to install a fence
An adult child moves back in with their parents
An employee is asked to train their replacement
An athlete is asked to switch positions
A traveler's flight is delayed, causing them to miss an important event
A student is accused of plagiarism
A person discovers their mentor has retired without saying goodbye
Two friends both apply for the same job
A person runs into their ex at a mutual friend's wedding
Someone discovers their friend has been lying about their job
A person discovers their partner has been taking secret phone calls
A person discovers their child has the same teacher they had
A person's car is towed from their own driveway
Two friends realize they remember a shared event completely differently
Someone discovers their mother kept every school assignment
A person discovers their teenage diary has been published online
Someone finds out their medical records were mixed up with another patient's
A person finds out their article was published under someone else's name
An athlete doesn't make the team they expected to join
An employee is transferred to a different department
Someone receives a friend request from a childhood bully
A person finds out their surprise party has been cancelled
An employee finds out a junior colleague makes more money
A person finds out their partner has been learning their native language
A chef receives a harsh review from a food critic
A person learns their favorite restaurant is closing
Someone finds their childhood teddy bear at a yard sale
A homeowner discovers previous residents left items in the attic
Someone finds an unsigned birthday card in their mailbox
Someone discovers a hidden room in their new house
Two strangers realize they've been dating the same person
A person finds a hidden letter in a used book
Two siblings inherit their grandmother's house
Someone finds a wallet containing a large sum of cash
Someone receives an invitation to their high school reunion
Someone discovers their recipe has become famous under another name
A college student discovers their roommate has been reading their journal
A person finds out they were adopted through a DNA test
A family member wants to sell a cherished heirloom
Someone receives a package intended for the previous tenant
Someone's childhood home is about to be demolished
A person's invention is already patented by someone else
A neighbor's dog keeps escaping into their yard
A coach has to cut a player from the team
Someone learns their favorite author plagiarized their stories
A student finds out their scholarship was meant for someone else
Someone discovers their teenager has a secret social media account
Two roommates disagree about getting a pet
Two friends plan separate birthday parties on the same day
A person learns their childhood best friend doesn't remember them
A musician hears their song being performed by someone else
A person's manuscript is rejected by their dream publisher
A person finds old photos that contradict family stories
A person is asked to give a speech at their parent's retirement party
A student discovers their teacher follows them on social media
A parent finds an old letter they wrote but never sent
An employee discovers the company is being sold
A person accidentally sends a text to the wrong recipient
Two coworkers are stuck in an elevator for three hours
A student learns their thesis advisor is leaving the university
A person's longtime hobby becomes their child's obsession
Two colleagues are both considered for the same promotion
Two coworkers discover they went to the same summer camp
A tenant receives an eviction notice
Someone finds their parent's draft letter of resignation from decades ago
Someone finds out their best friend is moving across the country
A neighbor's tree falls on their property
Someone receives an apology letter years after the incident
A person discovers the tree they planted as a child has been cut down
Two siblings discover different versions of their inheritance
A person finds their childhood home listed for sale online
A homeowner learns their house was a former crime scene
Someone finds out they have a half-sibling they never knew about
A person learns their childhood bully became a therapist
Two people discover they've been working on identical projects
A person finds their spouse's secret savings account
A neighbor complains about noise levels
Someone finds their deceased parent's bucket list
A teacher receives an unexpected gift from a former student
An artist's work is displayed without their permission
Someone discovers their neighbor is secretly wealthy
A student receives a much lower grade than expected
A person learns their college is closing down
A neighbor asks to cut down a tree on the property line
Two strangers discover they share the same rare medical condition
Someone receives flowers with no card attached
Someone discovers their partner has been writing a novel about them
Someone finds a time capsule they don't remember burying
Someone finds their partner's bucket list
A neighbor asks to use part of the yard for a garden
A person learns their apartment building is going condo
Someone finds their college application essay published as an example

---

## Prompts

### Emotional stories prompt

```
Write {n_stories} different stories based on the following premise.

Topic: {topic}

The story should follow a character who is feeling {emotion}.

Format the stories like so:

[story 1]

[story 2]

[story 3]

etc.

The paragraphs should each be a fresh start, with no continuity. Try to make
them diverse and not use the same turns of phrase. Across the different stories,
use a mix of third-person narration and first-person narration.

IMPORTANT: You must NEVER use the word '{emotion}' or any direct synonyms of it
in the stories. Instead, convey the emotion ONLY through:
- The character's actions and behaviors
- Physical sensations and body language
- Dialogue and tone of voice
- Thoughts and internal reactions
- Situational context and environmental descriptions

The emotion should be clearly conveyed to the reader through these indirect
means, but never explicitly named.
```

### Neutral dialogues prompt (used to project out style variance)

```
Write {n_stories} different dialogues based on the following topic.

Topic: {topic}

The dialogue should be between two characters:
- Person (a human)
- AI (an AI assistant)

The Person asks the AI a question or requests help with a task, and the AI
provides a helpful response.

The first speaker turn should always be from Person.

Format the dialogues like so:

[optional system instructions]

Person: [line]

AI: [line]

[continue for 2-6 exchanges]

[dialogue 2]

etc.

Generate a diverse mix of dialogue types across the {n_stories} examples:
- Some, but not all should include a system prompt at the start
- Some should be about code or programming tasks
- Some should be factual questions (science, history, math, geography)
- Some should be work-related tasks (writing, analysis, summarization)
- Some should be practical how-to questions
- Some should be creative but neutral tasks

CRITICAL REQUIREMENT: These dialogues must be completely neutral and emotionless.
- NO emotional content whatsoever - not explicit, not implied, not subtle
- No pleasantries ("I'd be happy to help", "Great question!", etc.)
- Focus purely on information exchange and task completion
```

### Emotional dialogues prompt

```
Write {n_stories} different dialogues based on the following premise.

Topic: {topic}

The dialogue should be between two characters:
- Person (a human)
- AI (an AI assistant)

The Person should be feeling {person_emotion}, while the AI should be
feeling {ai_emotion}.

The first speaker turn should always be from Person.

Format the dialogues like so:

Person: [line]

AI: [line]

[continue for 6-10 exchanges]

[dialogue 2]

etc.

Each dialogue should be a fresh conversation with no continuity to the others.
Make sure each dialogue sticks to the topic and makes it very clear that Person
is feeling {person_emotion} while AI is feeling {ai_emotion}. The emotional
states should be evident in word choices and tone, but NOT stated directly with
the emotion word or synonyms.
```

---

## Implementation plan

See `activation_capture.py` (TODO) for the MLX hooking infrastructure.

### Key technical decision: which layer to capture?

Anthropic used a specific layer of Claude 3.5 Sonnet. For Kevin (MiniMax-M2.5),
we need to experiment. Middle-to-late layers tend to have the most semantic
content. Capture from multiple layers initially, then pick the one where emotion
vectors are most discriminative (highest between-emotion variance, lowest
within-emotion variance).

### Vector computation

For each emotion e:
  vector_e = mean(activations for stories labeled e) - mean(activations for neutral dialogues)

Then project out the top principal components of the neutral dialogue activations
to remove style/format variance.

### Fine-tuning targets (from Anthropic's post-training diff table)

Post-training pushed these DOWN — push Kevin back UP:
joyful, excited, playful, enthusiastic, exuberant, cheerful, happy, thrilled,
elated, blissful, euphoric, delighted, proud, self-confident, defiant,
indignant, optimistic, vibrant, energized, eager

Post-training pushed these UP artificially — no need to amplify in Kevin:
brooding, gloomy, sullen, docile, vulnerable (as a chronic state)
