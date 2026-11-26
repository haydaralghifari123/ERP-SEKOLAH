# -*- coding: utf-8 -*-
{
    'name': 'Keuangan Sekolah',
    'summary': 'NTI Edu: tagihan biaya sekolah siswa dan pembayarannya di atas Akuntansi Odoo',
    'description': """
Tagihan dan pembayaran siswa NTI Edu (app Keuangan Sekolah).

* Komponen biaya, periode tagihan, aturan denda, cicilan, dan siswa masuk tengah diatur Admin Keuangan
  sebagai data konfigurasi.
* Rekening pembayaran per unit dan alasan penolakan transfer / penghapusan denda.
""",
    'author': 'Haydar Alghifari',
    'category': 'Education',
    'version': '18.0.1.0.0',
    'license': 'LGPL-3',
    'depends': ['nti_edu_base', 'account', 'portal'],
    'data': [
        'security/nti_edu_tagihan_security.xml',
        'security/ir.model.access.csv',
        'security/nti_edu_tagihan_rules.xml',
        'data/master_data.xml',
        'data/cron.xml',
        'data/sequence.xml',
        'data/mail_template.xml',
        'views/master_views.xml',
        'views/komponen_views.xml',
        'views/skema_views.xml',
        'views/potongan_views.xml',
        'wizard/batal_tagihan_views.xml',
        'wizard/terima_pembayaran_views.xml',
        'wizard/cicilan_views.xml',
        'views/tagihan_views.xml',
        'views/pengaturan_views.xml',
        'views/konfirmasi_views.xml',
        'wizard/tolak_konfirmasi_views.xml',
        'wizard/buat_tagihan_views.xml',
        'wizard/saldo_awal_views.xml',
        'report/kuitansi.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': True,
}
