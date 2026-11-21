"""Recipients that cannot receive transactional email."""

RESERVED_SUFFIXES = (".test", ".example", ".invalid", ".localhost", ".local")
BLOCKED_DOMAINS = frozenset(
    {
        "example.com",
        "example.net",
        "example.org",
        "copperfinch.ng",
        "junipercourt.ng",
        "mangogrove.ng",
        "dovecrescent.ng",
        "astervale.ng",
        "cedarbay.ng",
        "oriolebooks.ng",
        "sableridge.ng",
        "lindenharbour.ng",
        "beryllane.ng",
        "marulakitchens.ng",
    }
)
BLOCKED_ADDRESSES = frozenset(
    {
        "hauwa.sani@terraxmedia.com",
        "chiamaka.obi@terraxmedia.com",
        "olumide.fashola@terraxmedia.com",
        "ibrahim.danjuma@terraxmedia.com",
        "efe.okoro@terraxmedia.com",
        "temitope.ojo@terraxmedia.com",
        "aisha.garba@terraxmedia.com",
    }
)


def is_undeliverable_recipient(address: str) -> bool:
    local, separator, domain = address.strip().casefold().rpartition("@")
    domain = domain.rstrip(".")
    return (
        not separator
        or not local
        or not domain
        or f"{local}@{domain}" in BLOCKED_ADDRESSES
        or any(domain == suffix[1:] or domain.endswith(suffix) for suffix in RESERVED_SUFFIXES)
        or any(domain == blocked or domain.endswith("." + blocked) for blocked in BLOCKED_DOMAINS)
    )
