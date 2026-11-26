# -*- coding: utf-8 -*-
import psycopg2

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.misc import format_date

GRUP_BENDAHARA = 'nti_edu_tagihan.group_tagihan_bendahara'


class SaldoAwalWizard(models.TransientModel):
    """Tunggakan Awal (spec §4.3): tunggakan dari sebelum Tagihan Mulai dimasukkan sebagai tagihan biasa bertanda
    `nti_edu_saldo_awal`. Tiap baris diproses sendiri; baris yang gagal tetap di wizard beserta galatnya."""
    _name = 'nti_edu.tagihan.saldo.awal.wizard'
    _description = 'Wizard Tunggakan Awal'

    baris_ids = fields.One2many('nti_edu.tagihan.saldo.awal.wizard.baris', 'wizard_id', string='Tunggakan')
    ada_galat = fields.Boolean(compute='_compute_ada_galat')

    @api.depends('baris_ids.galat')
    def _compute_ada_galat(self):
        for rec in self:
            rec.ada_galat = any(rec.baris_ids.mapped('galat'))

    def action_simpan(self):
        self.ensure_one()
        baris_semua = self.baris_ids
        if not baris_semua:
            raise UserError(_('Isi minimal satu baris tunggakan.'))
        self.env['nti_edu.tagihan.akses']._nti_edu_cek_hak(GRUP_BENDAHARA, baris_semua.siswa_id.sudo().company_id)
        Move = self.env['account.move']
        berhasil = self.env['nti_edu.tagihan.saldo.awal.wizard.baris']
        for baris in baris_semua:
            try:
                with self.env.cr.savepoint():
                    baris._terbitkan(Move)
            except psycopg2.OperationalError:
                raise
            except UserError as e:  # termasuk ValidationError
                baris.galat = e.args[0] if e.args else str(e)
            else:
                berhasil |= baris
        jumlah = len(berhasil)
        berhasil.unlink()
        if self.baris_ids:
            # Baris yang gagal tetap tampil beserta galatnya untuk diperbaiki lalu disimpan ulang.
            return {
                'type': 'ir.actions.act_window',
                'name': _('Tunggakan Awal'),
                'res_model': self._name,
                'res_id': self.id,
                'view_mode': 'form',
                'target': 'new',
            }
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Tunggakan Awal'),
                'message': _('%s tagihan tunggakan awal diterbitkan.', jumlah),
                'type': 'success',
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }


class SaldoAwalWizardBaris(models.TransientModel):
    _name = 'nti_edu.tagihan.saldo.awal.wizard.baris'
    _description = 'Baris Wizard Tunggakan Awal'

    wizard_id = fields.Many2one(
        'nti_edu.tagihan.saldo.awal.wizard', string='Wizard', required=True, ondelete='cascade')
    siswa_id = fields.Many2one(
        'res.partner', string='Siswa', required=True, domain="[('nti_edu_is_siswa', '=', True)]")
    komponen_id = fields.Many2one(
        'nti_edu.tagihan.komponen', string='Komponen Biaya', required=True, domain="[('jenis', '=', 'biaya')]")
    periode = fields.Date(
        string='Periode', help='Tanggal awal periode tunggakan (mis. 1 Mei untuk SPP Mei). Untuk komponen sekali '
                               'menjadi tanggal terbit.')
    jatuh_tempo = fields.Date(
        string='Jatuh Tempo', compute='_compute_jatuh_tempo', store=True, readonly=False,
        help='Bawaan = periode.')
    nominal = fields.Float(string='Sisa Tunggakan', required=True, digits='Account')
    galat = fields.Char(string='Galat', readonly=True)

    @api.depends('periode')
    def _compute_jatuh_tempo(self):
        for rec in self:
            rec.jatuh_tempo = rec.periode

    def _terbitkan(self, Move):
        """Terbitkan tagihan tunggakan baris ini; `UserError` bila baris tidak valid atau tagihan sudah ada."""
        self.ensure_one()
        siswa = self.siswa_id.sudo()
        komponen = self.komponen_id.sudo()
        unit = siswa.company_id
        if komponen.jenis != 'biaya':
            raise UserError(_('Komponen "%s" bukan komponen biaya.', komponen.name))
        if komponen.company_id and komponen.company_id not in unit.parent_ids:
            raise UserError(_('Komponen "%(komponen)s" tidak berlaku di unit %(unit)s.',
                              komponen=komponen.name, unit=unit.name))
        if self.nominal <= 0:
            raise UserError(_('Sisa tunggakan harus lebih dari nol.'))
        sekali = komponen.periode_jenis_id.dasar == 'sekali'
        if not sekali and not self.periode:
            raise UserError(_('Periode wajib diisi untuk komponen "%s".', komponen.name))
        jatuh_tempo = self.jatuh_tempo or self.periode
        if not jatuh_tempo:
            raise UserError(_('Isi periode atau jatuh tempo.'))
        periode = False if sekali else self.periode
        tanggal = self.periode or jatuh_tempo
        sekolah = {'periode': periode, 'saldo_awal': True}
        if periode:
            ta = self.env['nti_edu.tahun.ajaran'].sudo().search([
                ('tanggal_mulai', '<=', periode), ('tanggal_selesai', '>=', periode)], limit=1)
            if ta:
                sekolah['tahun_ajaran_id'] = ta
                sekolah['semester_id'] = ta.semester_ids.filtered(
                    lambda s: s.tanggal_mulai <= periode <= s.tanggal_selesai)[:1]
        keterangan = None
        if periode:
            keterangan = _('%(komponen)s %(periode)s (tunggakan awal)',
                           komponen=komponen.name, periode=format_date(self.env, periode, date_format='MMMM y'))
        return Move._nti_edu_terbitkan(
            siswa, komponen, self.nominal, tanggal, jatuh_tempo, keterangan=keterangan, **sekolah)
