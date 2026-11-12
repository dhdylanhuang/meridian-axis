"""Private admin SQL rejects noncanonical identities before interpolation."""

import pytest

from meridian.security.membership_admin import initial_membership_sql

SUBJECTS = ("11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222")


@pytest.mark.parametrize(
    "subjects",
    [
        (SUBJECTS[0], SUBJECTS[0]),
        (SUBJECTS[0], "x'; SELECT true; --"),
        (SUBJECTS[0], "22222222222242228222222222222222"),
        (SUBJECTS[0], None),
        (SUBJECTS[0],),
    ],
)
def test_rejects_invalid_subjects_without_echo(subjects):
    with pytest.raises(ValueError, match="^membership_subjects_invalid$"):
        initial_membership_sql(subjects)


def test_sql_is_secret_wrapped_and_excludes_emails():
    command = initial_membership_sql(SUBJECTS)
    assert SUBJECTS[0] not in repr(command) and SUBJECTS[1] not in repr(command)
    assert "@" not in command.get_secret_value()
