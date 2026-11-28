"""Common English given-name nicknames and spellings, each mapped to one formal name.

Used by the person_nickname_address rule (equity.matching.resolve): "BOB SMITH" and
"ROBERT SMITH" at the same address are one person to review. A plain table of name forms
(facts about names, no people in it). A nickname that is short for more than one formal
name (CHRIS: Christopher or Christine; PAT, SAM, ALEX, TED, HARRY, NATE, AL, ...) is left out, so
two different people at one address are never made one by it.
"""

from __future__ import annotations

# formal name -> its nicknames and other spellings of it (KATHERINE: CATHERINE, KATHRYN;
# ERIC: ERIK; CARL: KARL). Every entry appears once, and none is also a formal name.
GROUPS: dict[str, tuple[str, ...]] = {
    "AARON": ("ARON", "ARRON"),
    "ABRAHAM": ("ABE",),
    "ALAN": ("ALLEN", "ALLAN"),
    "ANN": ("ANNE",),
    "ANDREW": ("ANDY", "DREW"),
    "ANTHONY": ("TONY",),
    "ARTHUR": ("ART", "ARTIE"),
    "BARBARA": ("BARB", "BARBIE"),
    "BENJAMIN": ("BEN", "BENNY", "BENJI"),
    "BERNARD": ("BERNIE",),
    "BEVERLY": ("BEV",),
    "BRADLEY": ("BRAD",),
    "BRIAN": ("BRYAN",),
    "CARL": ("KARL",),
    "CHARLES": ("CHARLIE", "CHUCK", "CHAS"),
    "CHRISTOPHER": ("KRISTOPHER", "CHRISTOPHE"),
    "CYNTHIA": ("CINDY",),
    "DANIEL": ("DAN", "DANNY"),
    "DAVID": ("DAVE", "DAVEY"),
    "DEBORAH": ("DEB", "DEBBIE", "DEBRA"),
    "DONALD": ("DON", "DONNIE"),
    "DOROTHY": ("DOT", "DOTTIE"),
    "DOUGLAS": ("DOUG",),
    "EDWARD": ("ED", "EDDIE"),
    "ERIC": ("ERIK", "ERICK"),
    "ERICA": ("ERIKA",),
    "ELIZABETH": ("LIZ", "LIZZIE", "BETH", "BETTY", "BETSY", "ELIZA", "LIBBY"),
    "EUGENE": ("GENE",),
    "FREDERICK": ("FRED", "FREDDIE", "FREDDY"),
    "GERALD": ("GERRY",),
    "GREGORY": ("GREG",),
    "HERBERT": ("HERB",),
    "JACQUELINE": ("JACKIE",),
    "JAMES": ("JIM", "JIMMY", "JIMMIE"),
    "JEFFREY": ("JEFF", "JEFFERY"),
    "JENNIFER": ("JEN", "JENNY", "JENNI"),
    "JOHN": ("JACK", "JOHNNY"),
    "JONATHAN": ("JON", "JONATHON", "JOHNATHAN", "JOHNATHON"),
    "JOSEPH": ("JOE", "JOEY"),
    "JOSHUA": ("JOSH",),
    "KATHERINE": (
        "KATE",
        "KATIE",
        "KATHY",
        "KATHIE",
        "KITTY",
        "CATHY",
        "CATHIE",
        "CATHERINE",
        "KATHRYN",
        "CATHRYN",
        "KATHARINE",
    ),
    "KENNETH": ("KEN", "KENNY"),
    "LAWRENCE": ("LARRY",),
    "LEONARD": ("LEN", "LENNY"),
    "MARGARET": ("MAGGIE", "MEG", "PEGGY", "PEG", "MARGE", "MARGIE"),
    "MARK": ("MARC",),
    "MATTHEW": ("MATT", "MATHEW"),
    "MICHAEL": ("MIKE", "MIKEY", "MICK", "MICKEY", "MICHEAL"),
    "NICHOLAS": ("NICK", "NICKY"),
    "PATRICIA": ("PATTY", "PATSY", "TRISH", "TRICIA"),
    "PETER": ("PETE",),
    "PHILIP": ("PHIL", "PHILLIP"),
    "RACHEL": ("RACHAEL",),
    "RAYMOND": ("RAY",),
    "REBECCA": ("BECKY", "BECCA"),
    "RICHARD": ("RICK", "RICKY", "RICH", "RICHIE", "DICK"),
    "ROBERT": ("BOB", "BOBBY", "ROB", "ROBBIE"),
    "RONALD": ("RON", "RONNIE"),
    "RUSSELL": ("RUSS", "RUSTY"),
    "SAMUEL": ("SAMMY",),
    "SARAH": ("SARA",),
    "SEAN": ("SHAWN", "SHAUN"),
    "STEPHEN": ("STEVE", "STEVIE", "STEVEN"),
    "SUSAN": ("SUE", "SUSIE", "SUZY"),
    "TERESA": ("THERESA",),
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


# Two spellings of one name where one of them is also short for another name, so it cannot
# sit in GROUPS (JON is JONATHAN's nickname and JOHN spelled short). The one-letter typo
# rule, which never pairs two real first names, accepts these pairs.
SAME_NAME_PAIRS: tuple[tuple[str, str], ...] = (("JOHN", "JON"),)
