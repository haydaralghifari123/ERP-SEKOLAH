# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class TambahRombelWizard(models.TransientModel):
    _name = 'nti_edu.tambah.rombel.wizard'
    _description = 'Wizard Tambah Siswa ke Rombel'

    rombel_id = fields.Many2one('nti_edu.rombel', string='Rombel', required=True)
    siswa_ids = fields.Many2many(
        'res.partner', string='Siswa', domain=[('nti_edu_is_siswa', '=', True)],
        default=lambda self: self._default_siswa_ids())
    tanggal_masuk = fields.Date(
        string='Tanggal Masuk', compute='_compute_tanggal_masuk',
        store=True, readonly=False, compute_sudo=False)

    @api.model
    def _default_siswa_ids(self):
        if self.env.context.get('active_model') == 'res.partner':
            return [(6, 0, self.env.context.get('active_ids') or [])]
        return False

    @api.depends('rombel_id')
    def _compute_tanggal_masuk(self):
        hari_ini = fields.Date.context_today(self)
        for rec in self:
            tahun = rec.rombel_id.tahun_ajaran_id
            if tahun and not (tahun.tanggal_mulai <= hari_ini <= tahun.tanggal_selesai):
                rec.tanggal_masuk = tahun.tanggal_mulai
            else:
                rec.tanggal_masuk = hari_ini

    def action_tambah(self):
        self.ensure_one()
        if not self.sudo().siswa_ids:
            raise UserError(_('Pilih minimal satu siswa.'))
        if not self.tanggal_masuk:
            raise UserError(_('Tanggal masuk wajib diisi.'))
        rombel = self.rombel_id
        Anggota = self.env['nti_edu.rombel.anggota']
        # Validasi semua siswa dahulu dan kumpulkan masalah supaya tidak ada penambahan sebagian.
        masalah = []
        # Id yang tidak terbaca pemanggil bisa terbuang diam-diam oleh ORM (atau baru gagal saat dibaca):
        # cek ulang lewat search (aturan akses berlaku) terhadap pilihan tersimpan di wizard. active_ids
        # tidak dipakai: operator boleh mengurangi siswa di form, jadi hanya siswa_ids wizard yang sah.
        pilihan = set(self.sudo().siswa_ids.ids)  # hanya id; sudo agar id tak terbaca tidak memicu AccessError
        terbaca = self.env['res.partner'].with_context(active_test=False).search([('id', 'in', list(pilihan))])
        hilang = pilihan - set(terbaca.ids)
        if hilang:
            # Nama tidak ditampilkan karena memang tidak terbaca oleh pemanggil.
            masalah.append('- %s' % _(
                '%s kontak terpilih tidak dapat diakses atau bukan siswa', len(hilang)))
        for siswa in terbaca:
            if not siswa.nti_edu_is_siswa:
                alasan = _('bukan siswa')
            elif not siswa.active or siswa.nti_edu_status != 'aktif':
                alasan = _('status siswa tidak aktif')
            elif siswa.company_id != rombel.company_id:
                alasan = _('berbeda unit dengan rombel')
            elif Anggota.sudo().search_count([
                    ('siswa_id', '=', siswa.id), ('tahun_ajaran_id', '=', rombel.tahun_ajaran_id.id),
                    ('tanggal_keluar', '=', False)]):
                alasan = _('sudah menjadi anggota rombel pada tahun ajaran %s', rombel.tahun_ajaran_id.name)
            else:
                continue
            masalah.append('- %s: %s' % (siswa.name, alasan))
        if masalah:
            raise UserError(_(
                'Siswa berikut tidak bisa ditambahkan ke rombel "%(rombel)s":\n%(daftar)s',
                rombel=rombel.name, daftar='\n'.join(masalah)))
        # Dibuat sebagai user pemanggil (bukan sudo) agar ACL dan rule tetap berlaku.
        for siswa in terbaca:
            Anggota.create({
                'rombel_id': rombel.id, 'siswa_id': siswa.id, 'tanggal_masuk': self.tanggal_masuk})
        return {'type': 'ir.actions.act_window_close'}
