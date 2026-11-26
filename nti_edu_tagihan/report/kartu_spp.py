# -*- coding: utf-8 -*-
from odoo import _, api, models
from odoo.exceptions import AccessError, UserError

GRUP_PEMANTAU = 'nti_edu_tagihan.group_tagihan_pemantau'


class ReportKartuSpp(models.AbstractModel):
    """Kartu SPP siswa per tahun ajaran (spec §4.7). Tahun ajaran dari `data['tahun_ajaran_id']`, konteks
    `tahun_ajaran_id`, atau tahun ajaran aktif.

    Hak: Pemantau Keuangan (atau turunannya) yang boleh membaca siswa itu; pemanggil superuser (mis. portal, setelah
    memastikan siswa adalah anak pemanggil) dilewatkan. Data tagihan dibaca sebagai superuser.
    """
    _name = 'report.nti_edu_tagihan.report_kartu_spp'
    _description = 'Laporan Kartu SPP'

    @api.model
    def _get_report_values(self, docids, data=None):
        siswa = self.env['res.partner'].browse(docids)
        if not self.env.su:
            if not self.env.user.has_group(GRUP_PEMANTAU):
                raise AccessError(_('Anda tidak memiliki hak untuk mencetak Kartu SPP.'))
            siswa.check_access('read')
        siswa = siswa.sudo()
        bukan = siswa.filtered(lambda p: not p.nti_edu_is_siswa)
        if bukan:
            raise UserError(_('Kartu SPP hanya untuk siswa; %s bukan siswa.', ', '.join(bukan.mapped('name'))))
        TahunAjaran = self.env['nti_edu.tahun.ajaran'].sudo()
        ta_id = (data or {}).get('tahun_ajaran_id') or self.env.context.get('tahun_ajaran_id')
        ta = TahunAjaran.browse(ta_id).exists() if ta_id else TahunAjaran._get_aktif()
        if not ta:
            raise UserError(_('Tahun ajaran untuk Kartu SPP tidak ditemukan; aktifkan satu tahun ajaran.'))
        return {
            'doc_ids': siswa.ids,
            'doc_model': 'res.partner',
            'docs': siswa,
            'tahun_ajaran': ta,
            'kartu_spp': {s.id: s._nti_edu_data_kartu_spp(ta) for s in siswa},
            'label_status': {
                'lunas': _('Lunas'),
                'sebagian': _('Dibayar sebagian'),
                'belum': _('Belum dibayar'),
                'belum_terbit': _('Belum terbit'),
                'libur': _('Tidak ditagih'),
            },
        }
