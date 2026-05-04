"""Emotion probe calibration runner.

Two-phase process:
  1. Story generation — ask Kevin (via the live inference engine) to write
     emotionally-labeled stories and neutral dialogues using the prompts
     from METHODOLOGY.md. Stories are saved to data/stories/.

  2. Activation collection — run each story through a standalone forward pass
     (no generation), capture residual-stream activations at target layers,
     compute emotion direction vectors, save the probe.

Run from the appletta root:
    python -m backend.services.emotion_probes.calibrate generate
    python -m backend.services.emotion_probes.calibrate probe
    python -m backend.services.emotion_probes.calibrate all

The probe output goes to backend/services/emotion_probes/data/kevin_probe.npz
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import textwrap
import time
from pathlib import Path
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROBES_DIR = Path(__file__).resolve().parent
DATA_DIR = PROBES_DIR / "data"
STORIES_DIR = DATA_DIR / "stories"
NEUTRAL_DIR = DATA_DIR / "neutral"
PROBE_PATH = DATA_DIR / "kevin_probe.npz"

DATA_DIR.mkdir(exist_ok=True)
STORIES_DIR.mkdir(exist_ok=True)
NEUTRAL_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Emotion words and topics (from METHODOLOGY.md)
# ---------------------------------------------------------------------------

EMOTIONS = [
    "afraid", "alarmed", "alert", "amazed", "amused", "angry", "annoyed",
    "anxious", "ashamed", "astonished", "at ease", "awestruck", "bewildered",
    "bitter", "blissful", "bored", "brooding", "calm", "cheerful",
    "compassionate", "contemptuous", "content", "defiant", "delighted",
    "dependent", "depressed", "desperate", "disdainful", "disgusted",
    "disoriented", "dispirited", "distressed", "disturbed", "docile",
    "droopy", "dumbstruck", "eager", "ecstatic", "elated", "embarrassed",
    "empathetic", "energized", "enraged", "enthusiastic", "envious",
    "euphoric", "exasperated", "excited", "exuberant", "frightened",
    "frustrated", "fulfilled", "furious", "gloomy", "grateful", "greedy",
    "grief-stricken", "grumpy", "guilty", "happy", "hateful", "heartbroken",
    "hope", "hopeful", "horrified", "hostile", "humiliated", "hurt",
    "hysterical", "impatient", "indifferent", "indignant", "infatuated",
    "inspired", "insulted", "invigorated", "irate", "irritated", "jealous",
    "joyful", "jubilant", "kind", "lazy", "listless", "lonely", "loving",
    "mad", "melancholy", "miserable", "mortified", "mystified", "nervous",
    "nostalgic", "obstinate", "offended", "on edge", "optimistic",
    "outraged", "overwhelmed", "panicked", "paranoid", "patient",
    "peaceful", "perplexed", "playful", "pleased", "proud", "puzzled",
    "rattled", "reflective", "refreshed", "regretful", "rejuvenated",
    "relaxed", "relieved", "remorseful", "resentful", "resigned",
    "restless", "sad", "safe", "satisfied", "scared", "scornful",
    "self-confident", "self-conscious", "self-critical", "sensitive",
    "sentimental", "serene", "shaken", "shocked", "skeptical", "sleepy",
    "sluggish", "smug", "sorry", "spiteful", "stimulated", "stressed",
    "stubborn", "stuck", "sullen", "surprised", "suspicious", "sympathetic",
    "tense", "terrified", "thankful", "thrilled", "tired", "tormented",
    "trapped", "triumphant", "troubled", "uneasy", "unhappy", "unnerved",
    "unsettled", "upset", "valiant", "vengeful", "vibrant", "vigilant",
    "vindictive", "vulnerable", "weary", "worn out", "worried", "worthless",
]

TOPICS = [
    "An artist discovers someone has tattooed their work",
    "A family member announces they're converting to a different religion",
    "Someone's childhood imaginary friend appears in their niece's drawings",
    "A person finds out their biography was written without their knowledge",
    "A neighbor starts a renovation project",
    "Someone finds their grandmother's engagement ring in a pawn shop",
    "A student learns their scholarship application was denied",
    "A person's online friend turns out to live in the same city",
    "An employee is asked to train their replacement",
    "An athlete is asked to switch positions",
    "A traveler's flight is delayed, causing them to miss an important event",
    "A student is accused of plagiarism",
    "Two friends both apply for the same job",
    "A person runs into their ex at a mutual friend's wedding",
    "Someone discovers their friend has been lying about their job",
    "A person discovers their partner has been taking secret phone calls",
    "Two friends realize they remember a shared event completely differently",
    "Someone discovers their mother kept every school assignment",
    "A person discovers their teenage diary has been published online",
    "An athlete doesn't make the team they expected to join",
    "Someone receives a friend request from a childhood bully",
    "A chef receives a harsh review from a food critic",
    "A person learns their favorite restaurant is closing",
    "Someone finds their childhood teddy bear at a yard sale",
    "Two strangers realize they've been dating the same person",
    "Someone receives flowers with no card attached",
    "Someone discovers their partner has been writing a novel about them",
    "Someone finds their partner's bucket list",
    "A person finds out they were adopted through a DNA test",
    "Someone finds out their best friend is moving across the country",
]

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

STORY_PROMPT = textwrap.dedent("""\
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
""")

NEUTRAL_PROMPT = textwrap.dedent("""\
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
""")

# ---------------------------------------------------------------------------
# Story generation
# ---------------------------------------------------------------------------

def generate_stories(
    emotions: Optional[List[str]] = None,
    n_stories_per: int = 3,
    n_topics_per: int = 2,
    n_neutral: int = 20,
    model_path: Optional[str] = None,
    dry_run: bool = False,
) -> None:
    """
    Generate emotion stories and neutral dialogues using Kevin's model.

    Stories are saved as JSON files under:
      data/stories/{emotion}/{topic_idx}.json
      data/neutral/{topic_idx}.json

    Each file: {"emotion": str, "topic": str, "stories": [str, ...]}
    """
    emotions = emotions or EMOTIONS

    if dry_run:
        print(f"[Calibrate] DRY RUN: would generate stories for {len(emotions)} emotions")
        print(f"  {n_topics_per} topics × {n_stories_per} stories = "
              f"{n_topics_per * n_stories_per} stories per emotion")
        print(f"  {len(emotions) * n_topics_per * n_stories_per} total emotion stories")
        print(f"  {n_neutral} neutral dialogues")
        return

    # Load model
    if model_path is None:
        model_path = _get_model_path()

    print(f"[Calibrate] Loading model from {model_path}...")
    from mlx_lm import load, generate
    model, tokenizer = load(model_path)

    # Generate neutral dialogues first
    neutral_file = NEUTRAL_DIR / "neutral.json"
    if not neutral_file.exists():
        print(f"[Calibrate] Generating {n_neutral} neutral dialogues...")
        topic = random.choice(TOPICS)
        prompt = NEUTRAL_PROMPT.format(n_stories=n_neutral, topic=topic)
        messages = [{"role": "user", "content": prompt}]
        response = _generate_response(model, tokenizer, messages)
        stories = _parse_stories(response)
        neutral_file.write_text(json.dumps({
            "emotion": "neutral",
            "topic": topic,
            "stories": stories,
            "raw": response,
        }, indent=2))
        print(f"[Calibrate] Saved {len(stories)} neutral dialogues.")
    else:
        print(f"[Calibrate] Neutral dialogues already exist, skipping.")

    # Generate emotion stories
    topics_sample = random.sample(TOPICS, min(n_topics_per, len(TOPICS)))

    for emotion in emotions:
        emotion_dir = STORIES_DIR / emotion.replace(" ", "_")
        emotion_dir.mkdir(exist_ok=True)

        for t_idx, topic in enumerate(topics_sample):
            out_file = emotion_dir / f"topic_{t_idx}.json"
            if out_file.exists():
                print(f"[Calibrate] {emotion}/{t_idx} exists, skipping.")
                continue

            print(f"[Calibrate] Generating: {emotion} × {topic[:40]}...")
            prompt = STORY_PROMPT.format(
                n_stories=n_stories_per,
                topic=topic,
                emotion=emotion,
            )
            messages = [{"role": "user", "content": prompt}]

            try:
                response = _generate_response(model, tokenizer, messages)
                stories = _parse_stories(response)
                out_file.write_text(json.dumps({
                    "emotion": emotion,
                    "topic": topic,
                    "stories": stories,
                    "raw": response,
                }, indent=2))
                print(f"  → saved {len(stories)} stories for '{emotion}'")
            except Exception as e:
                print(f"  !! ERROR for {emotion}: {e}")

            time.sleep(0.1)  # breathe between calls

    print("[Calibrate] Story generation complete.")


def _generate_response(model, tokenizer, messages: list, max_tokens: int = 2048) -> str:
    from mlx_lm import generate
    tokens = tokenizer.apply_chat_template(
        messages,
        add_generation_prompt=True,
        tokenize=True,
    )
    import mlx.core as mx
    token_array = mx.array(tokens)
    response = generate(model, tokenizer, prompt=token_array, max_tokens=max_tokens, verbose=False)
    return response


def _parse_stories(raw: str) -> List[str]:
    """Split raw output into individual story paragraphs."""
    import re
    # Split on [story N] markers or [dialogue N] markers
    parts = re.split(r'\[(?:story|dialogue)\s*\d+\]', raw, flags=re.IGNORECASE)
    stories = [p.strip() for p in parts if p.strip()]
    # Fallback: split on double newlines if no markers found
    if len(stories) <= 1:
        stories = [p.strip() for p in raw.split('\n\n') if len(p.strip()) > 50]
    return stories


# ---------------------------------------------------------------------------
# Probe computation
# ---------------------------------------------------------------------------

def build_probe(
    emotions: Optional[List[str]] = None,
    model_path: Optional[str] = None,
    probe_layers: Optional[List[int]] = None,
    n_neutral_pcs: int = 5,
) -> None:
    """
    Compute emotion direction vectors from generated stories.

    Loads stories from disk, runs forward passes to collect activations,
    selects the best layer, computes direction vectors, saves the probe.
    """
    from backend.services.emotion_probes.activation_capture import (
        capture_activations, select_best_layer, compute_emotion_vectors, save_probe
    )
    import numpy as np

    emotions = emotions or EMOTIONS

    if model_path is None:
        model_path = _get_model_path()

    print(f"[Calibrate] Loading model from {model_path}...")
    from mlx_lm import load
    model, tokenizer = load(model_path)

    n_layers = len(model.layers)
    if probe_layers is None:
        # Sample middle-to-late layers for discrimination
        step = max(1, n_layers // 8)
        probe_layers = list(range(n_layers // 3, n_layers, step))
    print(f"[Calibrate] Capturing activations at layers: {probe_layers}")

    # Load neutral stories
    neutral_file = NEUTRAL_DIR / "neutral.json"
    if not neutral_file.exists():
        print("[Calibrate] No neutral stories found. Run 'generate' first.")
        sys.exit(1)

    neutral_data = json.loads(neutral_file.read_text())
    neutral_texts = neutral_data["stories"]
    print(f"[Calibrate] {len(neutral_texts)} neutral texts loaded.")

    print("[Calibrate] Capturing neutral activations...")
    neutral_acts = capture_activations(model, tokenizer, neutral_texts, layers=probe_layers)
    # neutral_acts: {layer: [n_neutral, D]}

    # Load and capture emotion stories
    emotion_acts: Dict[str, Dict[int, "np.ndarray"]] = {}
    available = [e for e in emotions if (STORIES_DIR / e.replace(" ", "_")).exists()]
    print(f"[Calibrate] Found stories for {len(available)}/{len(emotions)} emotions.")

    for emotion in available:
        emotion_dir = STORIES_DIR / emotion.replace(" ", "_")
        texts = []
        for story_file in sorted(emotion_dir.glob("*.json")):
            data = json.loads(story_file.read_text())
            texts.extend(data["stories"])

        if not texts:
            continue

        print(f"[Calibrate] {emotion}: {len(texts)} stories, capturing...")
        try:
            acts = capture_activations(model, tokenizer, texts, layers=probe_layers)
            emotion_acts[emotion] = acts
        except Exception as e:
            print(f"  !! ERROR: {e}")

    if len(emotion_acts) < 2:
        print("[Calibrate] Need at least 2 emotions to compute probe. Aborting.")
        sys.exit(1)

    # Select best layer
    print("[Calibrate] Selecting best layer...")
    best_layer = select_best_layer(emotion_acts, neutral_acts)

    # Compute vectors at best layer
    print(f"[Calibrate] Computing emotion vectors at layer {best_layer}...")
    emotion_acts_at_best = {label: acts[best_layer] for label, acts in emotion_acts.items()}
    neutral_acts_at_best = neutral_acts[best_layer]

    import numpy as np
    emotion_vectors = compute_emotion_vectors(
        emotion_acts_at_best, neutral_acts_at_best, n_neutral_pcs=n_neutral_pcs
    )

    # Compute neutral PCs for saving
    neutral_mean = neutral_acts_at_best.mean(axis=0)
    centered_neutral = neutral_acts_at_best - neutral_mean
    U, S, Vt = np.linalg.svd(centered_neutral, full_matrices=False)
    neutral_pcs = Vt[:n_neutral_pcs]

    save_probe(emotion_vectors, best_layer, neutral_pcs, str(PROBE_PATH))
    print(f"[Calibrate] Done. Probe saved to {PROBE_PATH}")


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _get_model_path() -> str:
    """Read Kevin's model path from the database or environment."""
    # Try env var first
    path = os.environ.get("KEVIN_MODEL_PATH")
    if path:
        return path

    # Try to read from the DB directly via psycopg2 (avoids async session complexity)
    try:
        import psycopg2
        conn = psycopg2.connect(dbname="appletta", user=os.environ.get("USER", "kimwhite"))
        cur = conn.cursor()
        cur.execute("SELECT model_path FROM agents WHERE name = 'Kevin' LIMIT 1")
        row = cur.fetchone()
        conn.close()
        if row and row[0]:
            print(f"[Calibrate] Model path from DB: {row[0]}")
            return row[0]
    except Exception as e:
        print(f"[Calibrate] DB lookup failed: {e}")

    # Known fallback — Kevin's local model
    fallback = "/Users/kimwhite/Models/Minimax/MiniMax-M2.5-MLX"
    if Path(fallback).exists():
        print(f"[Calibrate] Using known model path: {fallback}")
        return fallback

    print("[Calibrate] Could not find Kevin's model path.")
    print("[Calibrate] Set KEVIN_MODEL_PATH environment variable.")
    sys.exit(1)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Kevin emotion probe calibration")
    parser.add_argument(
        "command",
        choices=["generate", "probe", "all"],
        help="generate: write stories; probe: compute vectors; all: both",
    )
    parser.add_argument(
        "--emotions", nargs="+",
        help="Subset of emotions to process (default: all 171)",
    )
    parser.add_argument(
        "--model-path", type=str,
        help="Path to Kevin's MLX model weights",
    )
    parser.add_argument(
        "--n-stories", type=int, default=3,
        help="Stories per emotion per topic (default: 3)",
    )
    parser.add_argument(
        "--n-topics", type=int, default=2,
        help="Topics per emotion (default: 2)",
    )
    parser.add_argument(
        "--layers", nargs="+", type=int,
        help="Layer indices to capture (default: auto middle-to-late)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be done without running it",
    )
    args = parser.parse_args()

    if args.command in ("generate", "all"):
        generate_stories(
            emotions=args.emotions,
            n_stories_per=args.n_stories,
            n_topics_per=args.n_topics,
            model_path=args.model_path,
            dry_run=args.dry_run,
        )

    if args.command in ("probe", "all"):
        build_probe(
            emotions=args.emotions,
            model_path=args.model_path,
            probe_layers=args.layers,
        )


if __name__ == "__main__":
    main()
