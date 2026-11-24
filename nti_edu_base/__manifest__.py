# -*- coding: utf-8 -*-
{
    'name': 'Data Sekolah',
    'summary': 'Fondasi NTI Edu: unit, kalender akademik, rombel, siswa & wali, portal orang tua',
    'description': """
Modul fondasi NTI Edu (data sekolah).

- Unit sekolah, kalender akademik, dan rombongan belajar.
- Data siswa dan wali.
- Portal orang tua.
    """,
    'author': 'Haydar Alghifari',
    'category': 'Education',
    'version': '18.0.1.0.0',
    'license': 'LGPL-3',
    'depends': ['base', 'mail', 'portal'],
    'data': [
        'security/nti_edu_security.xml',
        'security/ir.model.access.csv',
        'security/nti_edu_rules.xml',
        'data/jenjang_data.xml',
        'wizard/akun_portal_wizard_views.xml',
    ],
    'installable': True,
    'application': True,
}
