# -*- coding: utf-8 -*-
# Copyright (c) 2017, Soldeva, SRL and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from fm.api import PENDING, FULLY_PAID, PARTIALLY_PAID, OVERDUE
from frappe.utils import flt

class TablaAmortizacion(Document):
	def update_status(self):
		orignal_duty = self.get_dutty_amount()

		today = frappe.utils.nowdate()
		grace_days = frappe.get_single("FM Configuration").grace_days
		due_date = frappe.utils.add_days(self.fecha, grace_days ) 
		# ok, let's see if the repayment has been fully paid
		if orignal_duty == self.monto_pendiente and str(due_date) < today:

			self.estado = OVERDUE
		elif  orignal_duty == self.monto_pendiente:

			self.estado = PENDING
		elif self.monto_pendiente <= 0.5:

			self.estado = FULLY_PAID
		elif self.monto_pendiente < orignal_duty and self.monto_pendiente > 0:

			self.estado = PARTIALLY_PAID

	def get_dutty_amount(self):
		return flt(self.cuota) + flt(self.insurance) + flt(self.fine)\
			- flt(self.fine_discount)

	def get_pending_amount(self):
		return self.get_dutty_amount() - flt(self.monto_pagado)

	def get_paid_in_others_vouchers(self, voucher):
		result = frappe.db.sql("""
			SELECT
				SUM(debit) 
			FROM
				`tabJournal Entry` AS parent 
				JOIN
					`tabJournal Entry Account` AS child 
					ON parent.name = child.parent 
			WHERE
				parent.pagare LIKE "%{0}%"
				AND repayment_field = "paid_amount" 
				AND parent.name != "{1}"
		""".format(self.name, voucher), as_list=True)

		return len(result) and result[0][0]
	
	def get_sibilings_paid_amount(self, voucher):
		result = frappe.db.sql("""
			SELECT
				SUM(monto_pagado) 
			FROM
				`tabTabla Amortizacion` AS parent 
			WHERE
				parent.name in "{}"
		""".format(self.name, voucher), as_list=True)

		return len(result) and result[0][0]

	def get_paid_amount_until(self, date):
		result = frappe.db.sql("""
			SELECT
				SUM(debit) AS paid_amount
			FROM
				`tabJournal Entry` AS parent 
				JOIN
					`tabJournal Entry Account` AS child 
					ON parent.name = child.parent 
			WHERE
				parent.pagare LIKE "%{0}%"
				AND repayment_field in ("capital","paid_amount")
				AND posting_date < "{1}" 

		""".format(self.name, date), as_list=True)

		return len(result) and result[0][0]

	def get_paid_in_sibilings(voucher, sibilings):
		result = frappe.db.sql("""
			SELECT
				SUM()
			
			""")

	def calculate_fine(self):
		import datetime
		conf = frappe.get_single("FM Configuration")
		fine_rate = flt(conf.vehicle_fine)/100
		grace_days = conf.grace_days
		# self.fine = 0
		tmp_fine = 0
		due_date = frappe.utils.add_days(self.fecha, grace_days)
		today = datetime.date.today()

		while self.monto_pendiente > 0 and due_date < today:
			dutty = self.get_dutty_amount()
			# dutty = flt(self.cuota) + flt(self.insurance) 
			paid_amount = flt(self.get_paid_amount_until(due_date))
			new_fine = (dutty - paid_amount) * fine_rate
			print("dutty {} paid_amount {} new fine {} due_date {}".format(dutty, paid_amount, new_fine, due_date))
			tmp_fine += new_fine
			due_date = frappe.utils.add_months(due_date, 1)

		return tmp_fine
