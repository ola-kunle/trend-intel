"""
Vertical ontology for the wellness / hypnosis / personal-development intelligence system.

This file is the single source of truth for:
  * what categories exist
  * what seed concepts we watch
  * how surface vocabulary maps onto a canonical concept
  * which concepts are scientifically established vs emerging vs interpretive vs unsubstantiated
  * which concepts are related-but-distinct (so we never collapse them)

Nothing here is decorative. The ontology drives:
  - relevance scoring (is this observation even about our vertical?)
  - concept resolution (raw text -> canonical concept key)
  - the evidence-tier badge shown in the dashboard
  - the safety filter that blocks content angles implying medical claims

Evidence tiers
--------------
established    clinically supported therapy / method with a real evidence base
emerging       promising but limited or preliminary research
adjacent       wellness/lifestyle practice, plausible, not a clinical treatment
interpretive   spiritual / consciousness framing, not a medical intervention
unsubstantiated  claims that exceed what the evidence supports

The tier is a *curatorial judgement*, not a measurement. It is stored with a
pointer to the kind of source a reader can go and check, so the dashboard can
show provenance rather than asserting authority.
"""

import re

# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

CATEGORIES = {
    "hypnosis": {
        "label": "Hypnosis & Subconscious Work",
        "blurb": "Hypnosis, hypnotherapy, subconscious reprogramming and guided practice.",
    },
    "mental_wellbeing": {
        "label": "Mental Wellbeing & Emotional Health",
        "blurb": "Stress, anxiety, burnout, emotional and nervous-system regulation.",
    },
    "self_development": {
        "label": "Personal Growth & Self-Development",
        "blurb": "Self-awareness, confidence, habits, identity and life transitions.",
    },
    "spirituality": {
        "label": "Spirituality & Consciousness",
        "blurb": "Consciousness exploration, energy work, manifestation, intuition.",
    },
    "relationships": {
        "label": "Relationships & Everyday Life",
        "blurb": "Attachment, boundaries, self-love, loneliness, career and meaning.",
    },
    "emerging_adjacent": {
        "label": "Emerging / Adjacent",
        "blurb": "Newly discovered subtopics: neuroplasticity, psychedelic research, longevity, AI-assisted reflection.",
    },
}

# ---------------------------------------------------------------------------
# Seed concepts
#   (canonical term, category, base relevance weight 0..1)
# ---------------------------------------------------------------------------

SEEDS = [
    # --- Hypnosis & subconscious ------------------------------------------
    ("quantum hypnosis", "hypnosis", 1.00),
    ("quantum healing hypnosis technique", "hypnosis", 1.00),
    ("qhht", "hypnosis", 0.95),
    ("hypnosis", "hypnosis", 1.00),
    ("hypnotherapy", "hypnosis", 1.00),
    ("past life regression", "hypnosis", 0.95),
    ("past life therapy", "hypnosis", 0.90),
    ("subconscious reprogramming", "hypnosis", 0.95),
    ("guided hypnosis", "hypnosis", 0.90),
    ("self hypnosis", "hypnosis", 0.95),
    ("hypnotic meditation", "hypnosis", 0.85),
    ("inner child work", "hypnosis", 0.85),
    ("inner child healing", "hypnosis", 0.85),
    ("belief transformation", "hypnosis", 0.80),
    ("emotional release technique", "hypnosis", 0.85),
    ("somatic experiencing", "hypnosis", 0.80),
    ("hypnotic induction", "hypnosis", 0.75),
    ("hypnosis for anxiety", "hypnosis", 0.95),
    ("hypnosis for sleep", "hypnosis", 0.95),
    ("hypnosis for trauma", "hypnosis", 0.85),
    ("shadow work", "hypnosis", 0.75),
    ("regression therapy", "hypnosis", 0.85),
    ("neuroplasticity", "emerging_adjacent", 0.85),
    ("neuroplasticity training", "emerging_adjacent", 0.80),
    ("cold exposure", "emerging_adjacent", 0.70),
    ("breathwork", "mental_wellbeing", 0.90),
    ("guided visualization", "mental_wellbeing", 0.85),
    ("therapeutic journaling", "mental_wellbeing", 0.80),
    ("embodiment practice", "emerging_adjacent", 0.70),
    ("sleep and dream exploration", "emerging_adjacent", 0.70),
    ("dream journaling", "emerging_adjacent", 0.70),
    ("digital wellness", "emerging_adjacent", 0.70),
    ("digital detox", "emerging_adjacent", 0.65),
    ("ai assisted self reflection", "emerging_adjacent", 0.75),
    ("women's wellness", "emerging_adjacent", 0.70),
    ("holistic lifestyle", "emerging_adjacent", 0.60),
    ("longevity", "emerging_adjacent", 0.60),
    ("holistic wellbeing", "emerging_adjacent", 0.65),
    ("psychedelic assisted therapy", "emerging_adjacent", 0.85),
    ("psychedelic therapy research", "emerging_adjacent", 0.80),
    ("ketamine therapy", "emerging_adjacent", 0.70),
    ("psilocybin therapy", "emerging_adjacent", 0.75),

    # --- Mental wellbeing -------------------------------------------------
    ("stress reduction", "mental_wellbeing", 0.90),
    ("anxiety management", "mental_wellbeing", 0.95),
    ("burnout recovery", "mental_wellbeing", 0.95),
    ("burnout", "mental_wellbeing", 0.90),
    ("emotional regulation", "mental_wellbeing", 0.95),
    ("nervous system regulation", "mental_wellbeing", 1.00),
    ("somatic healing", "mental_wellbeing", 0.90),
    ("trauma informed wellness", "mental_wellbeing", 0.80),
    ("mindfulness", "mental_wellbeing", 0.85),
    ("mindfulness based stress reduction", "mental_wellbeing", 0.85),
    ("sleep improvement", "mental_wellbeing", 0.90),
    ("emotional resilience", "mental_wellbeing", 0.85),
    ("stress", "mental_wellbeing", 0.80),
    ("anxiety", "mental_wellbeing", 0.85),
    ("panic attacks", "mental_wellbeing", 0.80),
    ("vagus nerve", "mental_wellbeing", 0.80),
    ("polyvagal theory", "mental_wellbeing", 0.80),
    ("fascia release", "mental_wellbeing", 0.70),
    ("tremoring", "mental_wellbeing", 0.70),
    ("sleep hygiene", "mental_wellbeing", 0.75),
    ("circadian rhythm", "mental_wellbeing", 0.70),
    ("cbt", "mental_wellbeing", 0.75),
    ("emdr", "mental_wellbeing", 0.80),
    ("cognitive behavioral therapy", "mental_wellbeing", 0.75),
    ("acceptance and commitment therapy", "mental_wellbeing", 0.70),
    ("act therapy", "mental_wellbeing", 0.60),
    ("IFS therapy", "mental_wellbeing", 0.70),
    ("internal family systems", "mental_wellbeing", 0.70),
    ("shadow work therapy", "mental_wellbeing", 0.60),
    ("bedroom coaching", "mental_wellbeing", 0.55),
    ("toxic positivity", "mental_wellbeing", 0.65),
    ("self compassion", "mental_wellbeing", 0.80),
    ("mental health", "mental_wellbeing", 0.85),

    # --- Self development -------------------------------------------------
    ("self discovery", "self_development", 0.95),
    ("self awareness", "self_development", 0.95),
    ("confidence building", "self_development", 0.90),
    ("limiting beliefs", "self_development", 0.95),
    ("self worth", "self_development", 0.95),
    ("identity transformation", "self_development", 0.80),
    ("habit formation", "self_development", 0.85),
    ("motivation", "self_development", 0.80),
    ("personal transformation", "self_development", 0.90),
    ("finding purpose", "self_development", 0.90),
    ("life transitions", "self_development", 0.85),
    ("self improvement", "self_development", 0.85),
    ("personal growth", "self_development", 0.85),
    ("goal setting", "self_development", 0.75),
    ("imposter syndrome", "self_development", 0.75),
    ("decision making", "self_development", 0.70),
    ("procrastination", "self_development", 0.75),
    ("mindset", "self_development", 0.75),
    ("adhd coaching", "self_development", 0.70),
    ("journaling", "self_development", 0.80),
    ("gratitude practice", "self_development", 0.70),
    ("values clarification", "self_development", 0.70),
    ("emotional intelligence", "self_development", 0.75),
    ("assertiveness", "self_development", 0.70),
    ("self sabotage", "self_development", 0.75),

    # --- Spirituality & consciousness --------------------------------------
    ("consciousness exploration", "spirituality", 0.95),
    ("spiritual awakening", "spirituality", 0.95),
    ("meditation", "spirituality", 0.85),
    ("energy healing", "spirituality", 0.90),
    ("reiki", "spirituality", 0.85),
    ("manifestation", "spirituality", 0.90),
    ("law of attraction", "spirituality", 0.85),
    ("higher self", "spirituality", 0.80),
    ("intuition", "spirituality", 0.80),
    ("human potential", "spirituality", 0.85),
    ("mind body connection", "spirituality", 0.85),
    ("quantum spirituality", "spirituality", 0.80),
    ("shadow work meditation", "spirituality", 0.70),
    ("energy work", "spirituality", 0.80),
    ("chakra", "spirituality", 0.80),
    ("aura", "spirituality", 0.65),
    ("astrology", "spirituality", 0.65),
    ("numerology", "spirituality", 0.55),
    ("sound healing", "spirituality", 0.80),
    ("solfeggio", "spirituality", 0.60),
    ("binaural beats", "spirituality", 0.70),
    ("meditation retreat", "spirituality", 0.75),
    ("non duality", "spirituality", 0.70),
    ("presence", "spirituality", 0.60),
    ("flow state", "spirituality", 0.70),
    ("plant medicine", "spirituality", 0.60),
    ("sacred plant medicine", "spirituality", 0.55),
    ("psychedelic journey", "spirituality", 0.70),
    ("past life", "spirituality", 0.70),
    ("regression", "spirituality", 0.60),

    # --- Relationships & everyday life -------------------------------------
    ("attachment style", "relationships", 0.95),
    ("attachment theory", "relationships", 0.85),
    ("self love", "relationships", 0.95),
    ("boundaries", "relationships", 0.90),
    ("emotional awareness", "relationships", 0.80),
    ("relationship healing", "relationships", 0.85),
    ("loneliness", "relationships", 0.90),
    ("career transition", "relationships", 0.85),
    ("life dissatisfaction", "relationships", 0.85),
    ("emotional exhaustion", "relationships", 0.90),
    ("finding meaning", "relationships", 0.85),
    ("codependency", "relationships", 0.85),
    ("toxic relationships", "relationships", 0.85),
    ("divorce recovery", "relationships", 0.75),
    ("grief", "relationships", 0.75),
    ("perfectionism", "relationships", 0.75),
    ("people pleasing", "relationships", 0.80),
    ("emotional abuse", "relationships", 0.75),
    ("parenting stress", "relationships", 0.70),
    ("mindful parenting", "relationships", 0.70),
    ("empty nest", "relationships", 0.60),
    ("quarter life crisis", "relationships", 0.65),
    ("midlife crisis", "relationships", 0.60),
    ("meaning of life", "relationships", 0.70),
]

# ---------------------------------------------------------------------------
# Surface vocabulary -> canonical concept.
# Keys are normalised (lowercase, single-spaced). Values are canonical terms
# that must exist in SEEDS.
# ---------------------------------------------------------------------------

ALIASES = {
    # hypnosis
    "quantum healing hypnosis": "quantum healing hypnosis technique",
    "quantum healing hypnosis technique qhht": "quantum healing hypnosis technique",
    "qhht hypnosis": "quantum healing hypnosis technique",
    "quantum hypnosis technique": "quantum hypnosis",
    "quantum hypnosis therapy": "quantum hypnosis",
    "hypnotherapist": "hypnotherapy",
    "hypnotic therapy": "hypnotherapy",
    "hypnosis therapy": "hypnotherapy",
    "past life regression therapy": "past life regression",
    "past lives": "past life",
    "regression hypnosis": "regression therapy",
    "subconscious mind": "subconscious reprogramming",
    "rewiring the subconscious": "subconscious reprogramming",
    "self hypnosis for sleep": "hypnosis for sleep",
    "self hypnosis for anxiety": "hypnosis for anxiety",
    "sleep hypnosis": "hypnosis for sleep",
    "anxiety hypnosis": "hypnosis for anxiety",
    "hypnosis for trauma release": "hypnosis for trauma",
    "trauma release": "emotional release technique",
    "emotional release": "emotional release technique",
    "ert": "emotional release technique",
    "inner child healing work": "inner child healing",
    "inner child therapy": "inner child work",
    "hypnotic meditation": "hypnotic meditation",
    "meditative hypnosis": "hypnotic meditation",
    "somatic experiencing therapy": "somatic experiencing",
    "somatic therapy": "somatic healing",
    "nervous system reset": "nervous system regulation",
    "nervous system healing": "nervous system regulation",
    "regulate your nervous system": "nervous system regulation",
    "vagus nerve stimulation": "vagus nerve",
    "polyvagal": "polyvagal theory",
    "neuroplasticity exercises": "neuroplasticity training",
    "brain rewiring": "neuroplasticity training",

    # mental wellbeing
    "burnout recovery plan": "burnout recovery",
    "burnout treatment": "burnout recovery",
    "recovering from burnout": "burnout recovery",
    "burnout": "burnout",
    "managing anxiety": "anxiety management",
    "anxiety relief": "anxiety management",
    "anxiety help": "anxiety management",
    "stress management": "stress reduction",
    "stress relief": "stress reduction",
    "reduce stress": "stress reduction",
    "emotional regulation skills": "emotional regulation",
    "regulate emotions": "emotional regulation",
    "breathwork": "breathwork",
    "breathing exercises": "breathwork",
    "breath work": "breathwork",
    "box breathing": "breathwork",
    "coherent breathing": "breathwork",
    "mbsr": "mindfulness based stress reduction",
    "mindfulness based stress reduction": "mindfulness based stress reduction",
    "mindfulness meditation": "mindfulness",
    "guided visualization": "guided visualisation",
    "visualisation": "guided visualisation",
    "somatic practice": "somatic healing",
    "trauma informed care": "trauma informed wellness",
    "sleep hygiene tips": "sleep hygiene",
    "sleep quality": "sleep improvement",
    "better sleep": "sleep improvement",
    "insomnia relief": "sleep improvement",
    "emotional resilience": "emotional resilience",
    "mental health": "mental health",
    "mental wellbeing": "mental wellbeing",
    "emotional intelligence": "emotional intelligence",

    # self development
    "self discovery journey": "self discovery",
    "discovering yourself": "self discovery",
    "self awareness": "self awareness",
    "know yourself": "self awareness",
    "build confidence": "confidence building",
    "self confidence": "confidence building",
    "confidence": "confidence building",
    "limiting belief": "limiting beliefs",
    "belief change": "belief transformation",
    "shift your beliefs": "belief transformation",
    "self worth": "self worth",
    "worthiness": "self worth",
    "identity shift": "identity transformation",
    "identity change": "identity transformation",
    "habit building": "habit formation",
    "building habits": "habit formation",
    "motivation": "motivation",
    "staying motivated": "motivation",
    "personal growth": "personal growth",
    "self improvement": "self improvement",
    "self development": "self development",
    "purpose in life": "finding purpose",
    "life purpose": "finding purpose",
    "finding meaning in life": "finding purpose",
    "major life change": "life transitions",
    "life transition": "life transitions",
    "journaling for therapy": "therapeutic journaling",
    "therapeutic writing": "therapeutic journaling",
    "impostor syndrome": "imposter syndrome",
    "decision making": "decision making",
    "procrastination": "procrastination",
    "self sabotage": "self sabotage",
    "assertiveness training": "assertiveness",
    "values": "values clarification",
    "clarifying values": "values clarification",

    # spirituality
    "consciousness": "consciousness exploration",
    "exploring consciousness": "consciousness exploration",
    "spiritual awakening": "spiritual awakening",
    "awakening": "spiritual awakening",
    "meditation": "meditation",
    "meditate": "meditation",
    "energy healing": "energy healing",
    "healing energy": "energy healing",
    "reiki healing": "reiki",
    "reiki": "reiki",
    "manifesting": "manifestation",
    "manifest": "manifestation",
    "manifestation tips": "manifestation",
    "law of attraction": "law of attraction",
    "higher self": "higher self",
    "connecting with your higher self": "higher self",
    "intuition": "intuition",
    "human potential": "human potential",
    "mind body connection": "mind body connection",
    "mind body": "mind body connection",
    "quantum energy healing": "quantum spirituality",
    "quantum": "quantum spirituality",
    "energy work": "energy work",
    "chakra healing": "chakra",
    "chakras": "chakra",
    "sound bath": "sound healing",
    "sound healing": "sound healing",
    "binaural beats": "binaural beats",
    "flow": "flow state",
    "flow state": "flow state",
    "plant medicine": "plant medicine",
    "psychedelics for therapy": "psychedelic assisted therapy",
    "psychedelic assisted therapy": "psychedelic assisted therapy",
    "ketamine infusion": "ketamine therapy",
    "psilocybin": "psilocybin therapy",
    "nonduality": "non duality",
    "presence practice": "presence",

    # relationships
    "attachment styles": "attachment style",
    "anxious attachment": "attachment style",
    "avoidant attachment": "attachment style",
    "secure attachment": "attachment style",
    "self love": "self love",
    "loving yourself": "self love",
    "setting boundaries": "boundaries",
    "healthy boundaries": "boundaries",
    "relationship repair": "relationship healing",
    "healing in relationships": "relationship healing",
    "loneliness epidemic": "loneliness",
    "feeling lonely": "loneliness",
    "career change": "career transition",
    "changing careers": "career transition",
    "burnout at work": "emotional exhaustion",
    "meaning and direction": "finding meaning",
    "codependency": "codependency",
    "toxic relationship": "toxic relationships",
    "abusive relationships": "emotional abuse",
    "grief and loss": "grief",
    "perfectionism": "perfectionism",
    "people pleasing": "people pleasing",
    "mindful parenting": "mindful parenting",
    "quarter life": "quarter life crisis",
    "midlife": "midlife crisis",
    "existential crisis": "life dissatisfaction",
    "meaning of life": "meaning of life",
}

# ---------------------------------------------------------------------------
# Related-but-distinct concepts.
# These MUST NOT be collapsed together. We surface the relation explicitly so a
# reader can see that, e.g., nervous-system regulation and somatic healing
# overlap without being identical.
#   relation types: overlaps | adjacent | subset | often_confused_with
# ---------------------------------------------------------------------------

RELATED = {
    "nervous system regulation": [
        ("somatic healing", "overlaps"),
        ("emotional regulation", "overlaps"),
        ("vagus nerve", "often_confused_with"),
        ("breathwork", "subset"),
        ("polyvagal theory", "adjacent"),
    ],
    "somatic healing": [
        ("somatic experiencing", "subset"),
        ("nervous system regulation", "overlaps"),
        ("emotional release technique", "overlaps"),
    ],
    "emotional regulation": [
        ("nervous system regulation", "overlaps"),
        ("self compassion", "adjacent"),
        ("emotional intelligence", "adjacent"),
    ],
    "subconscious reprogramming": [
        ("limiting beliefs", "overlaps"),
        ("affirmations", "often_confused_with"),
        ("cbt", "adjacent"),
    ],
    "quantum hypnosis": [
        ("quantum healing hypnosis technique", "subset"),
        ("quantum spirituality", "often_confused_with"),
    ],
    "quantum healing hypnosis technique": [
        ("quantum hypnosis", "subset"),
        ("hypnotherapy", "adjacent"),
    ],
    "quantum spirituality": [
        ("quantum hypnosis", "often_confused_with"),
        ("energy healing", "overlaps"),
        ("manifestation", "overlaps"),
    ],
    "manifestation": [
        ("law of attraction", "subset"),
        ("self worth", "overlaps"),
        ("quantum spirituality", "overlaps"),
    ],
    "law of attraction": [
        ("manifestation", "subset"),
        ("self worth", "adjacent"),
    ],
    "reiki": [
        ("energy healing", "subset"),
        ("somatic healing", "often_confused_with"),
    ],
    "energy healing": [
        ("reiki", "subset"),
        ("sound healing", "overlaps"),
        ("somatic healing", "often_confused_with"),
    ],
    "trauma informed wellness": [
        ("emdr", "adjacent"),
        ("somatic experiencing", "adjacent"),
        ("cbt", "adjacent"),
    ],
    "psychedelic assisted therapy": [
        ("psychedelic therapy research", "subset"),
        ("ketamine therapy", "adjacent"),
        ("plant medicine", "overlaps"),
    ],
    "self love": [
        ("self worth", "overlaps"),
        ("self compassion", "overlaps"),
        ("boundaries", "adjacent"),
    ],
    "self worth": [
        ("self love", "overlaps"),
        ("limiting beliefs", "overlaps"),
        ("confidence building", "adjacent"),
    ],
    "burnout": [
        ("burnout recovery", "subset"),
        ("emotional exhaustion", "overlaps"),
        ("nervous system regulation", "adjacent"),
    ],
    "burnout recovery": [
        ("burnout", "subset"),
        ("emotional exhaustion", "overlaps"),
    ],
    "attachment style": [
        ("relationship healing", "adjacent"),
        ("codependency", "overlaps"),
    ],
}

# ---------------------------------------------------------------------------
# Discovery lexicon.
#
# Terms that are *not* curated concepts but are unambiguously in the vertical.
# A surface phrase that matches one of these but no curated concept is a
# candidate new concept: it gets its own identity, its own history and its
# own lifecycle instead of being force-fitted into a seed. This is how the
# system notices vocabulary it was not told about.
# ---------------------------------------------------------------------------

DISCOVERY_LEXICON = {
    # High-precision vertical terms. Used both as a relevance gate and as the
    # anchor for minting a new concept. Multi-word and unambiguous terms are
    # preferred; bare generic words ("loss", "meaning", "routine") were
    # removed because they produce false positives in a global news feed.
    "hypnosis", "hypnotherapy", "hypnotic", "hypnotised", "hypnotized",
    "subconscious", "unconscious mind", "reprogramming",
    "inner child", "shadow work", "shadow journaling",
    "somatic", "somatic experiencing", "somatic therapy", "somatic healing",
    "somatic practice", "embodiment", "bodywork", "trauma release",
    "trauma", "cptsd", "ptsd", "complex trauma",
    "nervous system", "nervous system regulation", "vagus nerve",
    "polyvagal", "window of tolerance",
    "burnout", "burnout recovery", "emotional exhaustion",
    "anxiety", "anxiety attack", "panic attack", "social anxiety",
    "depression", "depressed", "anhedonia", "mental health",
    "mental illness", "mental wellbeing", "mental wellness",
    "ocd", "adhd", "pmdd", "perimenopause", "menopause", "endometriosis",
    "stress", "stress response", "cortisol", "chronic stress",
    "therapy", "therapist", "counselling", "counseling", "psychotherapy",
    "mindfulness", "meditation", "mindful", "mbsr",
    "sleep", "sleep hygiene", "sleep improvement", "insomnia", "circadian",
    "sleep apnea", "sleep debt",
    "breathwork", "breathing exercises", "pranayama", "breathwork practice",
    "journaling", "journal prompts", "therapeutic journaling",
    "reiki", "energy healing", "energy work", "chakra", "chakras",
    "sound healing", "sound bath", "solfeggio",
    "manifestation", "manifesting", "manifest", "law of attraction",
    "abundance", "higher self", "intuition", "human potential",
    "self love", "self worth", "self esteem", "self confidence",
    "self care", "self development", "personal growth", "self improvement",
    "attachment style", "attachment theory", "codependency", "codependent",
    "boundaries", "emotional intelligence", "emotional regulation",
    "emotional processing", "emotional abuse", "toxic relationships",
    "loneliness", "grief", "bereavement",
    "toxic positivity", "doomscrolling", "doom scrolling",
    "wellness", "wellbeing", "well being", "holistic", "holistic health",
    "spiritual", "spirituality", "consciousness", "consciousness exploration",
    "spiritual awakening", "non duality", "mind body", "mind-body",
    "psilocybin", "ketamine", "iboga", "ayurveda",
    "neuroplasticity", "neuroplastic", "neuroscience", "brain rewiring",
    "emdr", "cbt", "cognitive behavioral therapy", "ifs therapy",
    "acceptance and commitment therapy", "act therapy",
    "life transition", "career transition", "quarter life", "midlife crisis",
    "burnout", "habit formation", "habit building", "values clarification",
    "mindful parenting", "attachment", "nervous system reset",
    "dream journaling", "lucid dreaming", "sleep and dream exploration",
    "guided visualization", "guided visualisation", "therapeutic journaling",
    "burnout treatment", "stress reduction", "stress management",
    "life dissatisfaction", "meaning of life", "finding meaning",
    "personal transformation", "identity transformation",
    "limiting beliefs", "subconscious reprogramming", "inner child healing",
    "emotional release technique", "past life regression", "past life",
    "hypnotic meditation", "self hypnosis", "sleep hypnosis",
    "vagus nerve stimulation", "cold exposure", "digital detox",
    "digital wellness", "longevity", "ai assisted self reflection",
    "guided meditation", "meditation retreat", "restorative practice",
}

# ---------------------------------------------------------------------------
# Evidence tiers.
# tier -> (label, short description, where a reader can check)
# ---------------------------------------------------------------------------

EVIDENCE_TIERS = {
    "established": {
        "label": "Established",
        "description": "Clinically supported method with a meaningful evidence base.",
        "check": "PubMed / Europe PMC systematic reviews; professional body guidance.",
    },
    "emerging": {
        "label": "Emerging research",
        "description": "Promising but limited or preliminary evidence.",
        "check": "Recent preprints / pilot studies; replication status unknown.",
    },
    "adjacent": {
        "label": "Adjacent / lifestyle",
        "description": "Plausible wellness practice. Not a clinical treatment.",
        "check": "Popular press and practitioner consensus rather than trial evidence.",
    },
    "interpretive": {
        "label": "Spiritual / interpretive",
        "description": "Meaning-making or energetic framing. Not a medical intervention.",
        "check": "Cultural and philosophical literature; not clinical literature.",
    },
    "unsubstantiated": {
        "label": "Unsubstantiated claim",
        "description": "Claims that exceed what the evidence supports.",
        "check": "Absence of credible evidence; treat content angles with care.",
    },
}

# Curated tier assignment for concepts where the distinction matters.
EVIDENCE_MAP = {
    # established
    "hypnotherapy": "established",
    "hypnosis for anxiety": "established",
    "hypnosis for sleep": "established",
    "hypnosis for trauma": "emerging",
    "past life regression": "interpretive",
    "past life therapy": "interpretive",
    "regression therapy": "interpretive",
    "cbt": "established",
    "cognitive behavioral therapy": "established",
    "emdr": "established",
    "mindfulness based stress reduction": "established",
    "acceptance and commitment therapy": "established",
    "act therapy": "established",
    "ifs therapy": "emerging",
    "internal family systems": "emerging",
    "trauma informed wellness": "established",
    "meditation": "established",
    "mindfulness": "established",
    "breathwork": "adjacent",
    "box breathing": "adjacent",
    "somatic experiencing": "emerging",
    "somatic healing": "emerging",
    "emotional release technique": "emerging",
    "nervous system regulation": "emerging",
    "polyvagal theory": "emerging",
    "vagus nerve": "established",
    "therapeutic journaling": "adjacent",
    "journaling": "adjacent",
    "sleep hygiene": "established",
    "circadian rhythm": "established",
    "cold exposure": "emerging",
    "neuroplasticity": "established",
    "neuroplasticity training": "emerging",
    "psychedelic assisted therapy": "emerging",
    "psychedelic therapy research": "emerging",
    "ketamine therapy": "emerging",
    "psilocybin therapy": "emerging",
    "plant medicine": "emerging",
    "sacred plant medicine": "interpretive",
    "meditation retreat": "adjacent",
    "digital detox": "adjacent",
    "digital wellness": "adjacent",
    "self compassion": "established",
    "emotional intelligence": "established",
    "emotional resilience": "adjacent",
    "habit formation": "established",
    "self awareness": "established",
    "self discovery": "adjacent",
    "mindfulness based stress reduction": "established",
    "guided visualization": "adjacent",
    "guided visualisation": "adjacent",
    "embodiment practice": "emerging",
    "sleep and dream exploration": "adjacent",
    "dream journaling": "adjacent",
    "longevity": "emerging",
    "holistic wellbeing": "adjacent",
    "holistic lifestyle": "adjacent",
    "women's wellness": "adjacent",
    "ai assisted self reflection": "emerging",
    "limiting beliefs": "adjacent",
    "belief transformation": "interpretive",
    "subconscious reprogramming": "interpretive",
    "affirmations": "interpretive",
    "hypnotic meditation": "emerging",
    "inner child work": "emerging",
    "inner child healing": "emerging",
    "shadow work": "emerging",
    "shadow work therapy": "emerging",
    "quantum hypnosis": "unsubstantiated",
    "quantum healing hypnosis technique": "unsubstantiated",
    "qhht": "unsubstantiated",
    "quantum spirituality": "interpretive",
    "energy healing": "interpretive",
    "energy work": "interpretive",
    "reiki": "interpretive",
    "manifestation": "interpretive",
    "law of attraction": "interpretive",
    "higher self": "interpretive",
    "chakra": "interpretive",
    "aura": "interpretive",
    "sound healing": "interpretive",
    "solfeggio": "unsubstantiated",
    "binaural beats": "adjacent",
    "astrology": "interpretive",
    "numerology": "interpretive",
    "non duality": "interpretive",
    "flow state": "adjacent",
    "flow": "adjacent",
    "presence": "adjacent",
}

# ---------------------------------------------------------------------------
# Safety: content angles that would constitute a medical claim, a therapeutic
# promise, or exploitation of a vulnerable audience are blocked outright.
# Matched case-insensitively against generated content-angle text.
# ---------------------------------------------------------------------------

CLAIM_BLOCKLIST = [
    "cure",
    "cures ",
    "will heal",
    "heals you",
    "guaranteed",
    "cure your",
    "eliminate your anxiety",
    "replace therapy",
    "better than therapy",
    "without medication",
    "stop taking your medication",
    "diagnose",
    "treatment for",
    "proven to treat",
    "miracle",
    "permanent fix",
    "you will never",
    "100% effective",
    "no side effects",
    "safe alternative to",
    "detox your",
    "reset your brain permanently",
]

# Concepts where we deliberately restrict what may be said.
RESTRICTED_CONCEPTS = {
    "quantum hypnosis",
    "quantum healing hypnosis technique",
    "qhht",
    "solfeggio",
    "binaural beats",
    "astrology",
    "numerology",
    "plant medicine",
    "sacred plant medicine",
}

# ---------------------------------------------------------------------------
# Vocabulary that indicates audience *intent* rather than mere interest.
# Used for the audience-question and intent classification.
# ---------------------------------------------------------------------------

INTENT_PATTERNS = {
    "problem_solving": [
        "how to", "how do i", "why am i", "why do i", "help me", "fix",
        "stop", "reduce", "improve", "get rid of", "struggling with",
        "dealing with", "coping with", "what works for", "anyone else",
    ],
    "seeking_practical": [
        "how to", "steps", "routine", "technique", "method", "protocol",
        "exercise", "practice", "guide", "for beginners", "at home", "diy",
    ],
    "considering_professional": [
        "therapist", "counsellor", "counselor", "psychologist", "session",
        "cost", "worth it", "should i see", "worth seeing", "near me",
        "find a", "is it worth",
    ],
    "looking_for_service": [
        "near me", "book", "booking", "session", "practitioner", "coach",
        "price", "pricing", "cost", "offer", "available", "appointment",
    ],
    "curious": [
        "what is", "what does", "how does", "why does", "meaning of",
        "difference between", "does it work", "is it real", "explained",
    ],
    "sharing_experience": [
        "my experience", "i tried", "i did", "for me", "helped me",
        "this worked", "years ago", "i went through", "my journey",
    ],
}


# Rough category attribution for discovery-lexicon terms, used to place
# automatically discovered concepts into a category. Anything not listed falls
# back to token overlap against the curated seeds.
LEXICON_CATEGORY = {
    "adhd": "self_development", "pmdd": "mental_wellbeing",
    "perimenopause": "mental_wellbeing", "menopause": "mental_wellbeing",
    "endometriosis": "mental_wellbeing",
    "burnout": "mental_wellbeing", "mental health": "mental_wellbeing",
    "mental illness": "mental_wellbeing", "mental wellbeing": "mental_wellbeing",
    "anxiety": "mental_wellbeing", "anxiety attack": "mental_wellbeing",
    "panic attack": "mental_wellbeing", "ptsd": "mental_wellbeing",
    "ocd": "mental_wellbeing", "depression": "mental_wellbeing",
    "depressed": "mental_wellbeing", "anhedonia": "mental_wellbeing",
    "stress": "mental_wellbeing", "cortisol": "mental_wellbeing",
    "trauma": "mental_wellbeing", "cptsd": "mental_wellbeing",
    "therapy": "mental_wellbeing", "therapist": "mental_wellbeing",
    "counselling": "mental_wellbeing", "counseling": "mental_wellbeing",
    "mindfulness": "mental_wellbeing", "meditation": "spirituality",
    "mindful": "mental_wellbeing", "sleep": "mental_wellbeing",
    "insomnia": "mental_wellbeing", "circadian": "mental_wellbeing",
    "nervous system": "mental_wellbeing", "vagus nerve": "mental_wellbeing",
    "polyvagal": "mental_wellbeing", "window of tolerance": "mental_wellbeing",
    "somatic": "mental_wellbeing", "embodiment": "emerging_adjacent",
    "bodywork": "mental_wellbeing", "trauma release": "hypnosis",
    "breathwork": "mental_wellbeing", "breathing": "mental_wellbeing",
    "pranayama": "mental_wellbeing", "breath": "mental_wellbeing",
    "hypnosis": "hypnosis", "hypnotherapy": "hypnosis",
    "hypnotic": "hypnosis", "subconscious": "hypnosis",
    "unconscious": "hypnosis", "reprogramming": "hypnosis",
    "inner child": "hypnosis", "shadow work": "hypnosis", "shadow": "hypnosis",
    "self love": "relationships", "self worth": "self_development",
    "self esteem": "self_development", "self confidence": "self_development",
    "attachment": "relationships", "codependent": "relationships",
    "codependency": "relationships", "boundaries": "relationships",
    "journaling": "self_development", "journal": "self_development",
    "gratitude": "self_development",
    "reiki": "spirituality", "energy healing": "spirituality",
    "energy work": "spirituality", "chakra": "spirituality",
    "aura": "spirituality", "sound healing": "spirituality",
    "manifest": "spirituality", "manifesting": "spirituality",
    "manifestation": "spirituality", "abundance": "spirituality",
    "law of attraction": "spirituality",
    "consciousness": "spirituality", "spiritual": "spirituality",
    "spirituality": "spirituality", "awakening": "spirituality",
    "higher self": "spirituality",
    "grief": "relationships", "bereavement": "relationships",
    "toxic positivity": "mental_wellbeing", "doomscrolling": "mental_wellbeing",
    "doom scrolling": "mental_wellbeing",
    "loneliness": "relationships", "lonely": "relationships",
    "isolation": "relationships",
    "holistic": "emerging_adjacent", "wellness": "emerging_adjacent",
    "wellbeing": "emerging_adjacent", "well being": "emerging_adjacent",
    "self care": "self_development",
    "habit": "self_development", "habits": "self_development",
    "routine": "self_development", "discipline": "self_development",
    "exhaustion": "mental_wellbeing", "resentment": "mental_wellbeing",
    "ego": "spirituality", "ego death": "spirituality",
    "letting go": "spirituality", "surrender": "spirituality",
    "psilocybin": "emerging_adjacent", "ketamine": "emerging_adjacent",
    "iboga": "emerging_adjacent", "ayurveda": "emerging_adjacent",
    "yoga": "emerging_adjacent",
    "neuroscience": "emerging_adjacent", "neuroplastic": "emerging_adjacent",
    "plasticity": "emerging_adjacent",
    "emotional intelligence": "self_development",
    "emotional regulation": "mental_wellbeing",
    "emotional processing": "mental_wellbeing",
    "purpose": "self_development", "meaning": "relationships",
    "identity": "self_development",
}

# Words dropped from the edges of an auto-discovered concept label.
_EDGE_STOP = {
    "a", "an", "the", "for", "to", "of", "and", "or", "with", "my", "your",
    "in", "on", "at", "is", "are", "be", "how", "what", "why", "can", "do",
    "does", "i", "it", "me", "we", "you", "that", "this", "as", "by", "from",
    "vs", "near", "to", "about",
}


_LEXICON_RE = re.compile(
    r"(?<![a-z0-9])(?:" + "|".join(
        re.escape(t) for t in sorted(DISCOVERY_LEXICON, key=len, reverse=True)) + r")(?![a-z0-9])")


def lexicon_match(text):
    """Return the discovery-lexicon term found in text (longest first), or None."""
    t = normalise(text)
    if not t:
        return None
    m = _LEXICON_RE.search(t)
    return m.group(0) if m else None


def mint_concept_label(text, max_words=5):
    """Build a stable, readable label for an auto-discovered concept.

    We take the window of words around the matched lexicon term rather than
    the whole title, so that "Somatic Exercises for a Regulated Nervous System"
    becomes "somatic exercises" rather than an unreadable slug.
    """
    t = normalise(text)
    term = lexicon_match(t)
    if not term:
        return None
    words = t.split()
    idx = 0
    for i, w in enumerate(words):
        if w == term or w.startswith(term) and not w[len(term):].isalpha():
            idx = i
            break
    window = words[idx: idx + max_words]
    while window and window[0] in _EDGE_STOP:
        window.pop(0)
    while window and window[-1] in _EDGE_STOP:
        window.pop()
    if not window:
        window = [term]
    return " ".join(window[:max_words])


def category_for_lexicon(term):
    return LEXICON_CATEGORY.get(term)


def discoverable(text):
    """True when the text carries an unmistakable vertical signal.

    Used to gate auto-discovery: a phrase only becomes a new concept if it
    contains a term that clearly belongs to this industry. Without this gate
    a global trending feed would mint concepts for every passing news item.
    """
    t = normalise(text)
    if not t:
        return False
    for term in DISCOVERY_LEXICON:
        if len(term) < 4:
            continue
        if re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", t):
            return True
    return False


def canonical(term):
    """Resolve a surface string to a canonical concept key (or None)."""
    t = normalise(term)
    if not t:
        return None
    if t in SEED_SET:
        return t
    if t in ALIASES:
        return ALIASES[t]
    return None


def normalise(text):
    """Lowercase, strip punctuation, collapse whitespace."""
    if not text:
        return ""
    out = []
    for ch in text.lower().strip():
        if ch.isalnum() or ch.isspace() or ch in "'-":
            out.append(ch)
        else:
            out.append(" ")
    return " ".join("".join(out).split())


SEED_SET = {t for t, _, _ in SEEDS}
SEED_META = {t: {"category": c, "weight": w} for t, c, w in SEEDS}
CATEGORY_OF = {t: c for t, c, _ in SEEDS}
WEIGHT_OF = {t: w for t, _, w in SEEDS}
ALL_SEEDS = [t for t, _, _ in SEEDS]

# Reverse map so we can tell whether a canonical term was user-supplied.
CONCEPT_IDS = {}
for _i, (_t, _c, _w) in enumerate(SEEDS):
    CONCEPT_IDS[_t] = _i + 1


def evidence_tier(concept):
    """Evidence tier for a concept, with a conservative default."""
    if concept in EVIDENCE_MAP:
        return EVIDENCE_MAP[concept]
    # Default by category: anything we did not curate is treated as adjacent,
    # never as established. This keeps the badge honest for newly discovered
    # (auto-discovered) concepts.
    return "adjacent"


def related(concept):
    return RELATED.get(concept, [])


def classify_intent(text):
    """Best-effort audience-intent classification from surface text."""
    t = normalise(text)
    if not t:
        return None
    scores = {}
    for label, pats in INTENT_PATTERNS.items():
        for p in pats:
            if p in t:
                scores[label] = scores.get(label, 0) + 1
    if not scores:
        return None
    return max(scores.items(), key=lambda kv: kv[1])[0]


def is_blocked_claim(text):
    """True if generated copy would make an unsupported medical claim."""
    t = " " + normalise(text) + " "
    for phrase in CLAIM_BLOCKLIST:
        if phrase in t:
            return True
    return False
