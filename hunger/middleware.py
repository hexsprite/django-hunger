from django.conf import settings
from django.http import HttpResponseRedirect
from hunger.models import InvitationCode
from hunger.signals import invite_used
from hunger.receivers import invitation_code_used

import logging
logger = logging.getLogger(__name__)

#setup signals
invite_used.connect(invitation_code_used)

def error_log(s):
    pass

class BetaMiddleware(object):
    """
    Add this to your ``MIDDLEWARE_CLASSES`` make all views except for
    those in the account application require that a user be logged in.
    This can be a quick and easy way to restrict views on your site,
    particularly if you remove the ability to create accounts.

    **Settings:**

    ``BETA_ENABLE_BETA``
        Whether or not the beta middleware should be used. If set to `False`
        the PrivateBetaMiddleware middleware will be ignored and the request
        will be returned. This is useful if you want to disable privatebeta
        on a development machine. Default is `True`.

    ``BETA_NEVER_ALLOW_VIEWS``
        A list of full view names that should *never* be displayed.  This
        list is checked before the others so that this middleware exhibits
        deny then allow behavior.

    ``BETA_ALWAYS_ALLOW_VIEWS``
        A list of full view names that should always pass through.

    ``BETA_ALWAYS_ALLOW_MODULES``
        A list of modules that should always pass through.  All
        views in ``django.contrib.auth.views``, ``django.views.static``
        and ``privatebeta.views`` will pass through unless they are
        explicitly prohibited in ``PRIVATEBETA_NEVER_ALLOW_VIEWS``

    ``BETA_REDIRECT_URL``
        The URL to redirect to.  Can be relative or absolute.
    """

    def __init__(self):
        self.enable_beta = getattr(settings, 'BETA_ENABLE_BETA', True)
        self.never_allow_views = getattr(settings, 'BETA_NEVER_ALLOW_VIEWS', [])
        self.always_allow_views = getattr(settings, 'BETA_ALWAYS_ALLOW_VIEWS', [])
        self.always_allow_modules = getattr(settings, 'BETA_ALWAYS_ALLOW_MODULES', [])
        self.redirect_url = getattr(settings, 'BETA_REDIRECT_URL', '/beta/')
        self.signup_views = getattr(settings, 'BETA_SIGNUP_VIEWS', [])
        self.signup_confirmation_view = getattr(settings, 'BETA_SIGNUP_CONFIRMATION_VIEW', '')
        self.signup_confirmation_url = getattr(settings, 'BETA_SIGNUP_CONFIRMATION_URL', '')
        self.signup_url = getattr(settings, 'BETA_SIGNUP_URL', '/register/')
        self.allow_flatpages = getattr(settings, 'BETA_ALLOW_FLATPAGES', [])

    def process_view(self, request, view_func, view_args, view_kwargs):
        if request.path in self.allow_flatpages or '%s/' % request.path in self.allow_flatpages:
            from django.contrib.flatpages.views import flatpage
            return flatpage(request, request.path_info)

        if not self.enable_beta:
            #Do nothing is beta is not activated
            return

        invitation_code = request.COOKIES.get('invitation_code', '')
        in_beta, exists = InvitationCode.validate_code(invitation_code)
        whitelisted_modules = ['django.contrib.auth.views',
                               'django.contrib.admin.sites',
                               'django.views.static',
                               'django.contrib.staticfiles.views',
                               'hunger.views']

        short_name = view_func.__class__.__name__
        if short_name == 'function':
            short_name = view_func.__name__
        full_view_name = '%s.%s' % (view_func.__module__, short_name)

        #Check modules
        if self.always_allow_modules:
            whitelisted_modules += self.always_allow_modules

        #if view in module then ignore - except if view is signup confirmation
        if '%s' % view_func.__module__ in whitelisted_modules and not full_view_name == self.signup_confirmation_view:
            error_log("whitelisted or signup confirmation view")
            return

        #Check views
        if full_view_name in self.never_allow_views:
            error_log("never allow views")
            return HttpResponseRedirect(self.redirect_url)

        if full_view_name in self.always_allow_views:
            error_log("always allow views")
            return

        if full_view_name == self.signup_confirmation_view or request.path == self.signup_confirmation_url:
            #signup completed - deactivate invitation code
            error_log("signup complete")
            request.session['beta_complete'] = True
            # invite_used.send(sender=self.__class__, user=request.user, invitation_code=invitation_code)
            return

        if request.user.is_authenticated() and full_view_name not in self.signup_views:
            error_log("user is authed")
            # User is logged in, or beta is not active, no need to check anything else.
            return

        if full_view_name == 'registration.views.register' and not in_beta:
            error_log("not in beta, trying to register")
            return HttpResponseRedirect(self.signup_url)

        if full_view_name in self.signup_views and in_beta:
            #if beta code is valid and trying to register then let them through
            error_log("has beta code trying to register")
            return
        else:
            # next_page = request.META.get('REQUEST_URI')
            next_page = request.path
            if in_beta:
                error_log("redirect to signup")
                return HttpResponseRedirect(getattr(settings, 'BETA_SIGNUP_ACCOUNT_URL', '/accounts/register'))
            else:
                error_log("redirect to redirect url")
                return HttpResponseRedirect(self.redirect_url + '?next=%s' % next_page)

    def process_response(self, request, response):
        try:
            if request.session.get('beta_complete', False):
                response.delete_cookie('invitation_code')
                request.session['beta_complete'] = None
        except AttributeError:
            pass
        return response
