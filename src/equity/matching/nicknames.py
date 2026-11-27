"""Common English given-name nicknames, each mapped to one formal name.

Used by the person_nickname_address rule (equity.matching.resolve): "BOB SMITH" and
"ROBERT SMITH" at the same address are one person to review. A plain table of name forms
(facts about names, no people in it). A nickname that is short for more than one formal
name (CHRIS: Christopher or Christine; PAT, SAM, ALEX, TED, HARRY, NATE, AL, ...) is left out, so
two different people at one address are never made one by it.
"""

from __future__ import annotations

# formal name -> its nicknames. Every nickname appears once, and no nickname is also a
# formal name in another group.
GROUPS: dict[str, tuple[str, ...]] = {
    "ABRAHAM": ("ABE",),
    "ANDREW": ("ANDY", "DREW"),
    "ANTHONY": ("TONY",),
    "ARTHUR": ("ART", "ARTIE"),
    "BARBARA": ("BARB", "BARBIE"),
    "BENJAMIN": ("BEN", "BENNY", "BENJI"),
    "BERNARD": ("BERNIE",),
    "BEVERLY": ("BEV",),
    "BRADLEY": ("BRAD",),
    "CATHERINE": ("CATHY", "CATHIE"),
    "CHARLES": ("CHARLIE", "CHUCK", "CHAS"),
    "CYNTHIA": ("CINDY",),
    "DANIEL": ("DAN", "DANNY"),
    "DAVID": ("DAVE", "DAVEY"),
    "DEBORAH": ("DEB", "DEBBIE", "DEBRA"),
    "DONALD": ("DON", "DONNIE"),
    "DOROTHY": ("DOT", "DOTTIE"),
    "DOUGLAS": ("DOUG",),
    "EDWARD": ("ED", "EDDIE"),
    "ELIZABETH": ("LIZ", "LIZZIE", "BETH", "BETTY", "BETSY", "ELIZA", "LIBBY"),
    "EUGENE": ("GENE",),
    "FREDERICK": ("FRED", "FREDDIE", "FREDDY"),
    "GERALD": ("GERRY",),
    "GREGORY": ("GREG",),
    "HERBERT": ("HERB",),
    "JACQUELINE": ("JACKIE",),
    "JAMES": ("JIM", "JIMMY", "JIMMIE"),
    "JEFFREY": ("JEFF",),
    "JENNIFER": ("JEN", "JENNY", "JENNI"),
    "JOHN": ("JACK", "JOHNNY"),
    "JONATHAN": ("JON",),
    "JOSEPH": ("JOE", "JOEY"),
    "JOSHUA": ("JOSH",),
    "KATHERINE": ("KATE", "KATIE", "KATHY", "KATHIE", "KITTY"),
    "KENNETH": ("KEN", "KENNY"),
    "LAWRENCE": ("LARRY",),
    "LEONARD": ("LEN", "LENNY"),
    "MARGARET": ("MAGGIE", "MEG", "PEGGY", "PEG", "MARGE", "MARGIE"),
    "MATTHEW": ("MATT",),
    "MICHAEL": ("MIKE", "MIKEY", "MICK", "MICKEY"),
    "NICHOLAS": ("NICK", "NICKY"),
    "PATRICIA": ("PATTY", "PATSY", "TRISH", "TRICIA"),
    "PETER": ("PETE",),
    "PHILIP": ("PHIL",),
    "RAYMOND": ("RAY",),
    "REBECCA": ("BECKY", "BECCA"),
    "RICHARD": ("RICK", "RICKY", "RICH", "RICHIE", "DICK"),
    "ROBERT": ("BOB", "BOBBY", "ROB", "ROBBIE"),
    "RONALD": ("RON", "RONNIE"),
    "RUSSELL": ("RUSS", "RUSTY"),
    "SAMUEL": ("SAMMY",),
    "STEPHEN": ("STEVE", "STEVIE", "STEVEN"),
    "SUSAN": ("SUE", "SUSIE", "SUZY"),
    "THEODORE": ("THEO",),
    "THOMAS": ("TOM", "TOMMY"),
    "TIMOTHY": ("TIM", "TIMMY"),
    "VICTORIA": ("VICKY", "VICKIE", "TORI"),
    "VINCENT": ("VINCE", "VINNY"),
    "WALTER": ("WALT", "WALLY"),
    "WILLIAM": ("BILL", "BILLY", "WILL", "WILLIE", "WILLY"),
    "ZACHARY": ("ZACH", "ZACK"),
}


def nickname_map() -> dict[str, str]:
    """nickname -> formal name, for every nickname in GROUPS."""
    out: dict[str, str] = {}
    for formal, nicks in sorted(GROUPS.items()):
        for n in nicks:
            if n in out or n in GROUPS:
                raise ValueError(f"nickname {n} is ambiguous")
            out[n] = formal
    return out
