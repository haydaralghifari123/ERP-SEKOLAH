# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class TagihanTunggakanWali(models.TransientModel):
    """Baris baca-saja menu "Tunggakan Rombel Saya" (spec §4.7): tunggakan siswa rombel yang diwalikan user.

    Wali kelas tidak punya hak atas tagihan; baris dibuat sebagai superuser oleh `action_buka_tunggakan_rombel`
    setelah memastikan user adalah wali kelas rombel itu, dan hanya memuat nama siswa, rombel, komponen, sisa, dan
    jatuh tempo. Tiap user hanya melihat barisnya sendiri (rule `user_id`).
    """
    _name = 'nti_edu.tagihan.tunggakan.wali'
    _description = 'Tunggakan Rombel Wali Kelas'
    _order = 'rombel, siswa_nama, jatuh_tempo, id'

    user_id = fields.Many2one(
        'res.users', string='Wali Kelas', required=True, readonly=True, index=True, ondelete='cascade',
        default=lambda self: self.env.uid)
    siswa_nama = fields.Char(string='Siswa', readonly=True)
    rombel = fields.Char(string='Rombel', readonly=True)
    komponen = fields.Char(string='Komponen', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Mata Uang', readonly=True)
    sisa = fields.Monetary(string='Sisa', readonly=True)
    jatuh_tempo = fields.Date(string='Jatuh Tempo', readonly=True)

    @api.model
    def _peringatan(self, pesan):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': _('Tunggakan Rombel Saya'), 'message': pesan, 'type': 'warning', 'sticky': False},
        }

    @api.model
    def action_buka_tunggakan_rombel(self):
        """Menu "Tunggakan Rombel Saya": tunggakan (lewat jatuh tempo) siswa aktif di rombel tahun ajaran aktif
        yang wali kelasnya user ini, di unit yang mengizinkan wali kelas melihat tunggakan. Selain itu peringatan."""
        user = self.env.user
        ta = self.env['nti_edu.tahun.ajaran'].sudo()._get_aktif()
        rombel = self.env['nti_edu.rombel'].sudo().search([
            ('wali_kelas_id', '=', user.id), ('tahun_ajaran_id', '=', ta.id)]) if ta else None
        if not rombel:
            return self._peringatan(_('Anda bukan wali kelas rombel pada tahun ajaran aktif.'))
        rombel = rombel.filtered(lambda r: r.company_id.nti_edu_wali_kelas_lihat_tunggakan)
        if not rombel:
            return self._peringatan(_('Unit sekolah Anda tidak mengizinkan wali kelas melihat tunggakan.'))

        Baris = self.sudo()
        Baris.search([('user_id', '=', user.id)]).unlink()
        hari_ini = fields.Date.context_today(self)
        Move = self.env['account.move'].sudo()
        nilai = []
        for r in rombel.sorted('name'):
            siswa = r.anggota_ids.filtered(lambda a: not a.tanggal_keluar).siswa_id
            if not siswa:
                continue
            for tagihan in Move.search([
                    ('company_id', '=', r.company_id.id), ('nti_edu_siswa_id', 'in', siswa.ids),
                    *Move._nti_edu_domain_tunggakan(hari_ini)], order='nti_edu_jatuh_tempo_terbuka, id'):
                nilai.append({
                    'user_id': user.id,
                    'siswa_nama': tagihan.nti_edu_siswa_id.name,
                    'rombel': r.name,
                    'komponen': tagihan.nti_edu_komponen_id.name,
                    'currency_id': tagihan.currency_id.id,
                    'sisa': tagihan.amount_residual,
                    'jatuh_tempo': tagihan.nti_edu_jatuh_tempo_terbuka,
                })
        baris = Baris.create(nilai)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Tunggakan Rombel Saya'),
            'res_model': self._name,
            'view_mode': 'list',
            'views': [(self.env.ref('nti_edu_tagihan.view_tunggakan_wali_list').id, 'list')],
            'domain': [('id', 'in', baris.ids)],
            'context': {'create': False, 'edit': False, 'delete': False},
            'target': 'current',
        }
