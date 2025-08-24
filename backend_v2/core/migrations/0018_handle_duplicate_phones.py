from django.db import migrations


def handle_duplicate_phones(apps, schema_editor):
    """
    Find clients with duplicate phone numbers and make them unique by appending a suffix.
    """
    Client = apps.get_model('core', 'Client')
    
    # Get all non-null phone numbers
    all_phones = Client.objects.filter(phone__isnull=False).values_list('phone', flat=True)
    
    # Find duplicates
    seen = set()
    duplicates = set()
    for phone in all_phones:
        if phone in seen and phone:
            duplicates.add(phone)
        else:
            seen.add(phone)
    
    # Handle each duplicate phone
    for dup_phone in duplicates:
        # Get all clients with this phone number
        clients = Client.objects.filter(phone=dup_phone).order_by('id')
        
        # Skip the first one (keep it as is)
        for i, client in enumerate(clients[1:], 1):
            # Append a suffix to make it unique
            client.phone = f"{dup_phone}_duplicate_{i}"
            client.save()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0017_alter_client_email'),
    ]

    operations = [
        migrations.RunPython(handle_duplicate_phones, migrations.RunPython.noop),
    ]
