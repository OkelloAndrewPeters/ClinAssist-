from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages
from .forms import RegisterForm, LoginForm, ProfileForm


def register_view(request):
    """
    Handle user registration.

    Flow:
        1. Prevent logged-in users from re-registering
        2. Validate registration form
        3. Create user
        4. Auto-login user after successful registration
        5. Redirect to patient dashboard
    """
    # Prevent authenticated users from accessing registration page
    if request.user.is_authenticated:
        return redirect("patients:list")
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f"Welcome, {user.first_name}! Your account has been created.")
            return redirect("patients:list")
    else:
        form = RegisterForm()
    return render(request, "accounts/register.html", {"form": form})

# =============================================================================
# USER LOGIN VIEW
# =============================================================================
def login_view(request):
    """
    Authenticate and log in a user.

    Flow:
        1. Block logged-in users from re-login
        2. Validate credentials
        3. Log user in
        4. Redirect to next page or dashboard
    """
    if request.user.is_authenticated:
        return redirect("patients:list")
    if request.method == "POST":
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            return redirect(request.GET.get("next", "patients:list"))
        else:
            messages.error(request, "Invalid username or password.")
    else:
        form = LoginForm()
    return render(request, "accounts/login.html", {"form": form})


# =============================================================================
# USER LOGOUT VIEW
# =============================================================================
def logout_view(request):
    """
    Log out the current user and redirect to login page.
    """

    logout(request)

    return redirect("accounts:login")


# =============================================================================
# USER PROFILE VIEW
# =============================================================================
@login_required
def profile_view(request):
    """
    View and update user profile information.

    Features:
        - Requires authentication
        - Allows updating user model fields
        - Displays success feedback after update
    """
    
    if request.method == "POST":
        form = ProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated.")
            return redirect("accounts:profile")
    else:
        form = ProfileForm(instance=request.user)
    return render(request, "accounts/profile.html", {"form": form})