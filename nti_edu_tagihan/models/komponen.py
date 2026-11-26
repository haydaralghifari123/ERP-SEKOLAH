# -*- coding: utf-8 -*-
from odoo import Command, _, api, fields, models
from odoo.exceptions import ValidationError


class TagihanKomponen(models.Model):
    _name = 'nti_edu.tagihan.komponen'
    _description = 'Komponen Biaya'
    _order = 'sequence, id'
    _check_company_auto = True

    name = fields.Char(string='Nama', required=True)
    kode = fields.Char(string='Kode')
    company_id = fields.Many2one(
        'res.company', string='Unit Sekolah', ondelete='cascade', help='Kosong = berlaku untuk semua unit.')
    sequence = fields.Integer(string='Urutan', default=10)
    active = fields.Boolean(string='Aktif', default=True)
    jenis = fields.Selection([
        ('biaya', 'Biaya'),
        ('denda', 'Denda'),
    ], string='Jenis', required=True, default='biaya',
        help='Komponen denda dipakai aturan denda dan tidak dimasukkan ke skema biaya.')
    periode_jenis_id = fields.Many2one(
        'nti_edu.tagihan.periode.jenis', string='Periode Tagihan', ondelete='restrict', check_company=True)
    aturan_masuk_id = fields.Many2one(
        'nti_edu.tagihan.aturan.masuk', string='Aturan Siswa Masuk Tengah', ondelete='restrict',
        check_company=True, default=lambda self: self.env.ref(
            'nti_edu_tagihan.aturan_masuk_penuh', raise_if_not_found=False))
    aturan_cicilan_id = fields.Many2one(
        'nti_edu.tagihan.aturan.cicilan', string='Aturan Cicilan', ondelete='restrict', check_company=True,
        help='Kosong = tidak boleh dicicil.')
    aturan_denda_id = fields.Many2one(
        'nti_edu.tagihan.aturan.denda', string='Aturan Denda', ondelete='restrict', check_company=True,
        help='Kosong = tanpa denda.')
    akun_pendapatan_id = fields.Many2one(
        'account.account', string='Akun Pendapatan', ondelete='restrict', check_company=True,
        domain="[('account_type', 'in', ('income', 'income_other'))]")
    product_id = fields.Many2one(
        'product.product', string='Produk', readonly=True, copy=False, ondelete='restrict',
        help='Produk layanan yang dibuat otomatis untuk baris tagihan.')

    # Master boleh tanpa company, milik yayasan (induk), atau milik unit pemakai.
    _check_company_domain = models.check_company_domain_parent_of

    @api.constrains('jenis', 'periode_jenis_id')
    def _cek_periode(self):
        for rec in self:
            if rec.jenis == 'biaya' and not rec.periode_jenis_id:
                raise ValidationError(_('Komponen biaya "%s" wajib memiliki periode tagihan.', rec.name))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        kategori = self.env.ref('nti_edu_tagihan.kategori_produk_biaya_sekolah', raise_if_not_found=False)
        for rec in records:
            # Admin Keuangan tidak punya hak produk: produk dibuat sebagai superuser.
            vals_produk = {
                'name': rec.name,
                'type': 'service',
                'sale_ok': False,
                'purchase_ok': False,
                'company_id': rec.company_id.id,
                'taxes_id': [Command.clear()],
                'supplier_taxes_id': [Command.clear()],
            }
            if kategori:
                vals_produk['categ_id'] = kategori.id
            rec.sudo().product_id = self.env['product.product'].sudo().create(vals_produk)
        records.filtered('akun_pendapatan_id')._sinkron_akun_produk()
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'name' in vals or 'company_id' in vals:
            for rec in self:
                rec.product_id.sudo().write({'name': rec.name, 'company_id': rec.company_id.id})
        if 'akun_pendapatan_id' in vals:
            self._sinkron_akun_produk()
        return res

    def _sinkron_akun_produk(self):
        """Pasang akun pendapatan sebagai akun pendapatan produk di company akun itu dan semua cabangnya."""
        for rec in self.filtered('product_id'):
            akun = rec.akun_pendapatan_id.sudo()
            if akun:
                companies = self.env['res.company'].sudo().search([('id', 'child_of', akun.company_ids.ids)])
            else:
                companies = self.env['res.company'].sudo().search([])
            produk = rec.product_id.sudo()
            for company in companies:
                produk.with_company(company).property_account_income_id = akun
