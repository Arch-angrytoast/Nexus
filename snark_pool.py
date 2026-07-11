import random
from datetime import datetime, timezone

SNARK_POOL = {
    "tier_1": [ # 0% - 20%
        "Not a drop in their veins.",
        "Completely immune to the allegations.",
        "We investigated and found absolutely nothing.",
        "A rare beacon of purity.",
        "Error 404: Energy not found.",
        "They wouldn't even know how to begin.",
        "Cleanest background check I've ever seen.",
        "Zero traces detected in the bloodstream.",
        "The jury finds the defendant: Not Guilty.",
        "Couldn't muster it if their life depended on it.",
        "Completely void of the sauce.",
        "Basically a saint in this category.",
        "Tragically lacking in this department."
    ],
    "tier_2": [ # 21% - 50%
        "Showing some mild symptoms.",
        "Flying just under the radar.",
        "We see right through that innocent act.",
        "A little bit suspicious, but we'll let it slide.",
        "Dipping their toes in the water.",
        "The test results came back 'maybe'.",
        "Nothing crazy, but definitely on the watchlist.",
        "Casual weekend enjoyer.",
        "It's a phase, they might grow out of it.",
        "Keeping it strictly part-time.",
        "Just enough to make you raise an eyebrow.",
        "Borderline behavior detected.",
        "They dabble when nobody is looking."
    ],
    "tier_3": [ # 51% - 80%
        "It is getting completely out of hand.",
        "The rumors were absolutely true.",
        "Radiating an uncomfortable amount of this energy.",
        "Certified menace in training.",
        "We need to stage an intervention.",
        "Highly radioactive levels detected.",
        "It's not a phase, it's a lifestyle.",
        "They wake up and choose this.",
        "A concerning lack of self-awareness.",
        "The allegations have been confirmed.",
        "This is getting deeply problematic.",
        "You can smell it from a mile away.",
        "Operating at highly dangerous levels."
    ],
    "tier_4": [ # 81% - 100%
        "Off the charts. Seek immediate professional help.",
        "Practically writing the curriculum at this point.",
        "An absolute menace to society.",
        "The CEO of this exact energy.",
        "God tier. We should all be terrified.",
        "FBI's Most Wanted list for this category.",
        "Their power level is completely unrestrained.",
        "A biological weapon of this exact vibe.",
        "They are the final boss.",
        "I don't even know how they are still functioning.",
        "Lock them up and throw away the key.",
        "A walking, talking hazard sign.",
        "They invented it. Everyone else is just copying them."
    ]
}

STUPID_REPLIES = [
    "Dumbass!! This hasn't been coded yet.",
    "Are you typing with your elbows? That meter doesn't exist.",
    "Did you just smash your face on the keyboard? Invalid meter.",
    "I'm Nexus, not a mind reader. Try a meter that actually exists.",
    "My circuits are frying just trying to understand what you want.",
    "Congratulations, you found the secret 'Invalid Meter' easter egg! (Just kidding, you typed it wrong).",
    "Have you tried turning it off and on again? Oh wait, you just typed a bad meter name.",
    "Error 404: Brain cells not found. Try a real meter.",
    "Is this your first day on the internet? That meter isn't in the database.",
    "I would measure that for you, if it existed in this reality.",
    "Wow. Just... wow. Try `!help` or something.",
    "Typing is hard, isn't it? Let's try again with a valid meter."
]


def calculate_meter(target_id: int, meter_name: str, db_conn=None):
    utc_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    # Check for an override if a DB connection is provided
    score = None
    if db_conn:
        cursor = db_conn.cursor()
        cursor.execute("SELECT score FROM score_overrides WHERE target_id = ? AND meter_name = ? AND utc_date = ?", (target_id, meter_name, utc_date))
        row = cursor.fetchone()
        if row:
            score = row[0]

    if score is None:
        # Generate daily seed
        seed_string = f"{target_id}{meter_name}{utc_date}"

        # Generate score
        random.seed(seed_string)
        score = random.randint(0, 100)

        # Reset seed for true randomness on snark selection
        random.seed()

    # Progress bar (10 blocks)
    red_blocks = score // 10
    black_blocks = 10 - red_blocks
    progress_bar = "🟥" * red_blocks + "⬛" * black_blocks

    # Select snark
    if score <= 20:
        snark = random.choice(SNARK_POOL["tier_1"])
    elif score <= 50:
        snark = random.choice(SNARK_POOL["tier_2"])
    elif score <= 80:
        snark = random.choice(SNARK_POOL["tier_3"])
    else:
        snark = random.choice(SNARK_POOL["tier_4"])

    return score, progress_bar, snark
