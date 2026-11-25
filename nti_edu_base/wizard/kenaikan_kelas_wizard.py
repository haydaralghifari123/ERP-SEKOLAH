# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class KenaikanKelasWizard(models.TransientModel):
    _name = 'nti_edu.kenaikan.kelas.wizard'
    _description = 'Wizard Kenaikan Kelas'

    rombel_asal_id = fields.Many2one('nti_edu.rombel', string='Rombel Asal', required=True)
    rombel_tujuan_id = fields.Many2one(
        'nti_edu.rombel', string='Rombel Tujuan', help='Dipakai sebagai tujuan bawaan semua baris.')
    baris_ids = fields.One2many(
        'nti_edu.kenaikan.kelas.baris', 'wizard_id', string='Siswa',
        compute='_compute_baris_ids', store=True, readonly=False, compute_sudo=False)
    state = fields.Selection([('draft', 'Draf'), ('selesai', 'Selesai')], default='draft')

    @api.depends('rombel_asal_id', 'rombel_tujuan_id')
    def _compute_baris_ids(self):
        for rec in self:
            if rec.rombel_asal_id and not rec.rombel_asal_id.has_access('read'):
                rec.baris_ids = [(5, 0, 0)]
                continue
            aksi = 'lulus' if rec.rombel_asal_id.tingkat_id.is_akhir else 'naik'
            anggota = rec.rombel_asal_id.anggota_ids.filtered(lambda a: not a.tanggal_keluar)
            rec.baris_ids = [(5, 0, 0)] + [(0, 0, {
                'siswa_id': a.siswa_id.id,
                'aksi': aksi,
                'rombel_tujuan_id': rec.rombel_tujuan_id.id,
            }) for a in anggota]

    def action_proses(self):
        self.ensure_one()
        if self.state == 'selesai':
            raise UserError(_('Kenaikan kelas ini sudah diproses.'))
        asal = self.rombel_asal_id
        Anggota = self.env['nti_edu.rombel.anggota']
        # Validasi seluruh baris dahulu supaya tidak ada pemrosesan sebagian.
        for baris in self.baris_ids:
            if baris.aksi in ('naik', 'tinggal'):
                tujuan = baris.rombel_tujuan_id
                if not tujuan:
                    raise UserError(_('Rombel tujuan untuk siswa "%s" wajib diisi.', baris.siswa_id.name))
                if tujuan.tahun_ajaran_id == asal.tahun_ajaran_id:
                    raise UserError(_(
                        'Rombel tujuan "%s" harus berada pada tahun ajaran yang berbeda dari rombel asal.',
                        tujuan.name))
                if tujuan.tahun_ajaran_id.tanggal_mulai < asal.tahun_ajaran_id.tanggal_mulai:
                    raise UserError(_(
                        'Rombel tujuan "%(rombel)s" untuk siswa "%(siswa)s" berada pada tahun ajaran '
                        'yang lebih awal dari rombel asal.',
                        rombel=tujuan.name, siswa=baris.siswa_id.name))
                if baris.aksi == 'naik' and tujuan.tingkat_id.urutan <= asal.tingkat_id.urutan:
                    raise UserError(_(
                        'Rombel tujuan "%(rombel)s" untuk siswa "%(siswa)s" harus bertingkat lebih tinggi '
                        'dari rombel asal; pilih "Tinggal Kelas" bila siswa mengulang.',
                        rombel=tujuan.name, siswa=baris.siswa_id.name))
                if tujuan.company_id != asal.company_id:
                    raise UserError(_('Rombel tujuan "%s" harus berada pada unit yang sama.', tujuan.name))
                if Anggota.sudo().search_count([
                        ('siswa_id', '=', baris.siswa_id.id), ('tahun_ajaran_id', '=', tujuan.tahun_ajaran_id.id),
                        ('tanggal_keluar', '=', False)]):
                    raise UserError(_(
                        'Siswa "%(siswa)s" sudah menjadi anggota rombel pada tahun ajaran %(tahun)s.',
                        siswa=baris.siswa_id.name, tahun=tujuan.tahun_ajaran_id.name))
        # Hari keluar bersifat eksklusif: siswa lulus tetap anggota pada hari terakhir tahun ajaran.
        tanggal_keluar = asal.tahun_ajaran_id.tanggal_selesai + timedelta(days=1)
        for baris in self.baris_ids:
            if baris.aksi in ('naik', 'tinggal'):
                Anggota.create({'rombel_id': baris.rombel_tujuan_id.id, 'siswa_id': baris.siswa_id.id})
            else:
                baris.siswa_id.nti_edu_status = 'lulus'
                asal.anggota_ids.filtered(
                    lambda a: a.siswa_id == baris.siswa_id and not a.tanggal_keluar
                ).tanggal_keluar = tanggal_keluar
        self.state = 'selesai'
        return {'type': 'ir.actions.act_window_close'}


class KenaikanKelasBaris(models.TransientModel):
    _name = 'nti_edu.kenaikan.kelas.baris'
    _description = 'Baris Kenaikan Kelas'

    wizard_id = fields.Many2one('nti_edu.kenaikan.kelas.wizard', required=True, ondelete='cascade')
    siswa_id = fields.Many2one('res.partner', string='Siswa', required=True)
    rombel_tujuan_id = fields.Many2one('nti_edu.rombel', string='Rombel Tujuan')
    aksi = fields.Selection([
        ('naik', 'Naik/Pindah Rombel'), ('tinggal', 'Tinggal Kelas'), ('lulus', 'Lulus'),
    ], string='Aksi', required=True, default='naik')
