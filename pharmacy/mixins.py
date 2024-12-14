from django.contrib.auth.mixins import UserPassesTestMixin
from django.core.exceptions import PermissionDenied

class RoleRequiredMixin(UserPassesTestMixin):
    allowed_roles = []

    def test_func(self):
        if not self.request.user.is_authenticated:
            return False
        try:
            user_role = self.request.user.userprofile.role
            return user_role in self.allowed_roles
        except:
            return False

    def handle_no_permission(self):
        raise PermissionDenied("You don't have permission to access this page.") 