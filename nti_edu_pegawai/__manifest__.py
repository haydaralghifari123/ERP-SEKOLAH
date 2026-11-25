# -*- coding: utf-8 -*-
{
    'name': 'Data Pegawai Sekolah',
    'summary': 'NTI Edu: data kepegawaian guru dan tenaga kependidikan di atas karyawan (hr)',
    'description': """
Data kepegawaian guru dan tenaga kependidikan NTI Edu.

- Profil per orang (NUPTK, NIP, status kepegawaian, pendidikan, sertifikasi) pada kontak kerja pegawai.
- Data per penempatan (jenis PTK, TMT) pada karyawan di unit sekolah.
    """,
    'author': 'Haydar Alghifari',
    'category': 'Education',
    'version': '18.0.1.0.0',
    'license': 'LGPL-3',
    'depends': ['nti_edu_base', 'hr'],
    'data': [
        'security/nti_edu_pegawai_security.xml',
        'security/ir.model.access.csv',
    ],
    'application': False,
    'installable': True,
}
