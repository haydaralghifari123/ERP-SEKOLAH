# -*- coding: utf-8 -*-
{
    'name': 'Data Pegawai Sekolah',
    'summary': 'NTI Edu: data kepegawaian guru dan tenaga kependidikan di atas karyawan (hr)',
    'description': """
Data kepegawaian guru dan tenaga kependidikan NTI Edu.

* Profil per orang (NUPTK, NIP, status kepegawaian, pendidikan, sertifikasi) pada kontak kerja pegawai.
* Data per penempatan (jenis PTK, TMT) pada karyawan di unit sekolah.

Data demo (opsional, di atas demo nti_edu_base) menambahkan data pegawai untuk akun demo dan akun HRD
(password sama dengan login):

- HRD Yayasan (SMP dan SMA): hrd.demo
- Operator Data Sekolah juga TU Pegawai, pegawai tenaga administrasi SMP: operator.demo
- Guru SMP dengan sertifikasi: guru1.demo
- Guru di SMP dan SMA (satu orang, dua penempatan): guru2.demo
- Kepala sekolah SMA: guru3.demo
- Tenaga administrasi SMA tanpa akun login: Tendik Tanpa Akun Demo
""",
    'author': 'Haydar Alghifari',
    'category': 'Education',
    'version': '18.0.1.0.0',
    'license': 'LGPL-3',
    'depends': ['nti_edu_base', 'hr'],
    'data': [
        'security/nti_edu_pegawai_security.xml',
        'security/ir.model.access.csv',
        'security/nti_edu_pegawai_rules.xml',
        'views/sertifikasi_views.xml',
        'views/hr_employee_views.xml',
        'wizard/akun_login_wizard_views.xml',
        'wizard/penempatan_wizard_views.xml',
        'views/menu.xml',
    ],
    'demo': [
        'demo/nti_edu_pegawai_demo.xml',
    ],
    'assets': {
        'web.assets_tests': ['nti_edu_pegawai/static/tests/tours/**/*'],
    },
    'application': False,
    'installable': True,
}
