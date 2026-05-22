"""
URL configuration for mysite project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from myapp import views as myapp_views

urlpatterns = [
    # Dashboard
    path('', myapp_views.dashboard, name='dashboard'),

    # Locations
    path('locations/', myapp_views.location_list, name='location_list'),
    path('locations/add/', myapp_views.add_location, name='add_location'),
    path('locations/edit/', myapp_views.add_location, name='edit_location'),
    path('locations/detail/', myapp_views.location_detail, name='location_detail'),
    path('locations/delete/', myapp_views.delete_location, name='delete_location'),
    path('locations/restore/', myapp_views.restore_location, name='restore_location'),
    # Companies
    path('companies/', myapp_views.company_list, name='company_list'),
    path('companies/add/', myapp_views.add_company, name='add_company'),
    path('companies/edit/', myapp_views.add_company, name='edit_company'),
    path('companies/detail/', myapp_views.company_detail, name='company_detail'),
    path('companies/delete/', myapp_views.delete_company, name='delete_company'),
    path('companies/restore/', myapp_views.restore_company, name='restore_company'),
    # Partners
    path('partners/', myapp_views.partner_list, name='partner_list'),
    path('partners/add/', myapp_views.add_partner, name='add_partner'),
    path('partners/edit/', myapp_views.add_partner, name='edit_partner'),
    path('partners/detail/', myapp_views.partner_detail, name='partner_detail'),
    path('partners/delete/', myapp_views.delete_partner, name='delete_partner'),
    path('partners/restore/', myapp_views.restore_partner, name='restore_partner'),
    # Users
    path('users/', myapp_views.user_list, name='user_list'),
    path('users/add/', myapp_views.add_user, name='add_user'),
    path('users/edit/', myapp_views.edit_user, name='edit_user'),
    path('users/detail/', myapp_views.user_detail, name='user_detail'),
    path('users/delete/', myapp_views.delete_user, name='delete_user'),
    path('users/restore/', myapp_views.restore_user, name='restore_user'),
    # Leads
    path('leads/', myapp_views.lead_list, name='lead_list'),
    path('leads/add/', myapp_views.add_lead, name='add_lead'),
    path('leads/edit/', myapp_views.add_lead, name='edit_lead'),
    path('clients/create-ajax/', myapp_views.create_client_ajax, name='create_client_ajax'),
    path('partners/create-ajax/', myapp_views.create_partner_ajax, name='create_partner_ajax'),
    path('sales-person/create-ajax/', myapp_views.create_sales_person_ajax, name='create_sales_person_ajax'),
    path('leads/delete/', myapp_views.delete_lead, name='delete_lead'),
    path('leads/restore/', myapp_views.restore_lead, name='restore_lead'),
    path('admin/', admin.site.urls),
]
