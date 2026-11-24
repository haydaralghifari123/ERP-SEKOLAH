# -*- coding: utf-8 -*-
{
    'name': 'Data Sekolah',
    'summary': 'Fondasi NTI Edu: unit, kalender akademik, rombel, siswa & wali, portal orang tua',
    'description': """
Modul fondasi NTI Edu (data sekolah).

- Unit sekolah, kalender akademik, dan rombongan belajar.
- Data siswa dan wali.
- Portal orang tua.

Data demo (opsional) memuat Yayasan Pendidikan Nusantara dengan SMP dan SMA, 20 siswa, dan akun berikut
(password sama dengan login):

- Operator Data Sekolah: operator.demo
- Guru (pengguna): guru1.demo (wali kelas VII-A), guru2.demo, guru3.demo
- Portal wali (dua anak di SMP dan SMA): wali.bersaudara@example.com
- Portal siswa: siswa.demo
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
    'demo': [
        'demo/nti_edu_demo.xml',
    ],
    'installable': True,
    'application': True,
}
