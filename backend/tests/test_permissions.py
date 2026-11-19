import pytest

from app.core.permissions import CompanyRole, OrgRole, Permission, can_assign_org_role, company_role_allows, permissions_for
from app.services.slugs import slugify


@pytest.mark.parametrize("role,perm,expected", [
    (CompanyRole.ORG_ADMIN, Permission.COMPANY_UPDATE, True),
    (CompanyRole.ACCOUNTANT, Permission.COMPANY_UPDATE, False),
    (CompanyRole.ACCOUNTANT, Permission.IMPORT_WRITE, True),
    (CompanyRole.CONTROLLER, Permission.IMPORT_WRITE, False),
    (CompanyRole.CONTROLLER, Permission.BUDGET_WRITE, True),
    (CompanyRole.ANALYST, Permission.BUDGET_WRITE, False),
    (CompanyRole.ANALYST, Permission.ANALYSIS_RUN, True),
    (CompanyRole.AUDITOR, Permission.ANALYSIS_RUN, False),
    (CompanyRole.AUDITOR, Permission.AUDIT_READ, True),
    (CompanyRole.VIEWER, Permission.COMPANY_READ, True),
    (CompanyRole.VIEWER, Permission.REPORT_GENERATE, False),
    (None, Permission.COMPANY_READ, False),
])
def test_company_matrix(role, perm, expected):
    assert company_role_allows(role, perm) is expected


def test_viewer_is_read_only():
    assert permissions_for("viewer") == ["company.read"]


def test_org_admin_has_everything():
    assert set(permissions_for("org_admin")) == {p.value for p in Permission}


@pytest.mark.parametrize("actor,target,current,expected", [
    (OrgRole.OWNER, OrgRole.OWNER, None, True),
    (OrgRole.ADMIN, OrgRole.MEMBER, None, True),
    (OrgRole.ADMIN, OrgRole.OWNER, None, False),
    (OrgRole.ADMIN, OrgRole.MEMBER, OrgRole.OWNER, False),   # rétrograder un owner
    (OrgRole.MEMBER, OrgRole.VIEWER, None, False),
    (OrgRole.VIEWER, OrgRole.VIEWER, None, False),
])
def test_role_assignment(actor, target, current, expected):
    assert can_assign_org_role(actor, target, current) is expected


@pytest.mark.parametrize("name,slug", [
    ("Cabinet Kouassi & Associés", "cabinet-kouassi-associes"),
    ("  SOCIÉTÉ   IVOIRIENNE  ", "societe-ivoirienne"),
    ("***", "organisation"),
])
def test_slugify(name, slug):
    assert slugify(name) == slug
