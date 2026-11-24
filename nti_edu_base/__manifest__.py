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
        'wizard/kenaikan_kelas_wizard_views.xml',
        'views/portal_templates.xml',
        'views/res_company_views.xml',
        'views/jenjang_views.xml',
        'views/jurusan_views.xml',
        'views/tahun_ajaran_views.xml',
        'views/hari_libur_views.xml',
        'views/mapel_views.xml',
        'views/ruang_views.xml',
        'views/rombel_views.xml',
        'views/siswa_views.xml',
        'views/wali_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': True,
}
