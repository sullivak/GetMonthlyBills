import time
import glob
import os
import re
import shutil
import csv
from selenium import webdriver
from selenium import common
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import PyPDF2


class BillScraper(object):

    def __init__(self, base_dir, csv_file):
        self.utes_base_dir = base_dir
        self.csv_file = csv_file
        self.download_dir = os.path.join(self.utes_base_dir, "_temp_")
        self.pw_data = {}
        self.page_wait_time = 10
        with open(self.csv_file, 'r') as f:
            reader = csv.reader(f)
            is_first_line = True
            for row in reader:
                if is_first_line:
                    is_first_line = False
                    continue
                self.pw_data[row[0]] = row[1:]

        # Set up new firefox profile to automatically download pdfs to specified dir (and disable internal displaying)
        fp = webdriver.FirefoxProfile()
        fp.set_preference("browser.download.folderList", 2)
        fp.set_preference("browser.download.manager.showWhenStarting", False)
        fp.set_preference("browser.download.dir", self.download_dir)
        fp.set_preference("browser.helperApps.neverAsk.saveToDisk", "application/pdf,application/x-pdf")
        fp.set_preference("pdfjs.disabled", True)
        fp.set_preference("plugin.scan.plid.all", False)
        fp.set_preference("plugin.scan.Acrobat", "99.0")

        self.browser = webdriver.Firefox(firefox_profile=fp)

    def __del__(self):
        self.browser.quit()

    def login(self, template_and_creds):
        """ method to fill out common login page (id, pw, button)
        :param template_and_creds: dictionary of dicts, one for each field: "userid", "pw", and "login_button"
        each field dict needs: "field_type", how to find, by "id" or "name"
                               "field_text", id or name text (e.g. "userId")
                               "input", what to feed field (not needed for submit button, which is just clicked)
        :return: True if it worked, else False
        """
        try:
            if template_and_creds["userid"]["field_type"] == "id":
                locator = (By.ID, template_and_creds["userid"]["field_text"])
            elif template_and_creds["userid"]["field_type"] == "name":
                locator = (By.NAME, template_and_creds["userid"]["field_text"])
            elif template_and_creds["userid"]["field_type"] == "link_text":
                locator = (By.LINK_TEXT, template_and_creds["userid"]["field_text"])
            else:
                raise ValueError("Currently unsupported field type: " + template_and_creds["userid"]["field_type"])
            user_id_field = WebDriverWait(self.browser, self.page_wait_time).until(
                EC.presence_of_element_located(locator)
            )
            user_id_field.send_keys(template_and_creds["userid"]["input"])
        except common.exceptions.TimeoutException:
            print "No user id!"
            return False
        except KeyError as e:
            print "Template and credentials missing required fields, could not find: "
            print e
            return False
        except ValueError as e:
            print e
            return False
    
        try:
            if template_and_creds["pw"]["field_type"] == "id":
                pw = self.browser.find_element_by_id(template_and_creds["pw"]["field_text"])
            elif template_and_creds["pw"]["field_type"] == "name":
                pw = self.browser.find_element_by_name(template_and_creds["pw"]["field_text"])
            elif template_and_creds["pw"]["field_type"] == "link_text":
                pw = self.browser.find_element_by_link_text(template_and_creds["pw"]["field_text"])
            else:
                raise ValueError("Currently unsupported field type: " + template_and_creds["pw"]["field_type"])
            pw.send_keys(template_and_creds["pw"]["input"])
        except common.exceptions.NoSuchElementException:
            print "No password!"
        except KeyError as e:
            print "Template and credentials missing required fields, could not find: "
            print e
            return False
        except ValueError as e:
            print e
            return False

        try:
            if template_and_creds["login_button"]["field_type"] == "id":
                submit = self.browser.find_element_by_id(template_and_creds["login_button"]["field_text"])
            elif template_and_creds["login_button"]["field_type"] == "name":
                submit = self.browser.find_element_by_name(template_and_creds["login_button"]["field_text"])
            elif template_and_creds["login_button"]["field_type"] == "link_text":
                submit = self.browser.find_element_by_link_text(template_and_creds["login_button"]["field_text"])
            else:
                raise ValueError("Currently unsupported field type: " + template_and_creds["login_button"]["field_type"])
            submit.click()
        except common.exceptions.NoSuchElementException:
            print "No login button!"
        except KeyError as e:
            print "Template and credentials missing required fields, could not find: "
            print e
            return False
        except ValueError as e:
            print e
            return False

        return True

    def get_att_bill(self):
        att_dir = os.path.join(self.utes_base_dir, "ATnT")
        att_login = {"userid": {"field_type": "id", "field_text": "userid", "input": self.pw_data["att"][0]},
                     "pw": {"field_type": "id", "field_text": "userPassword", "input": self.pw_data["att"][1]},
                     "login_button": {"field_type": "id", "field_text": "tguardLoginButton"}}
        self.browser.get("https://www.att.com/")
        self.login(att_login)

        # Second page, wait for View Payment Activity and click
        try:
            element = WebDriverWait(self.browser, self.page_wait_time).until(
                EC.presence_of_element_located((By.LINK_TEXT, "View Payment Activity"))
            )
            element.click()
        except common.exceptions.TimeoutException:
            print "No bill history!"

        # Third page, wait for Paper Bill button and click, pdf will download automatically
        try:
            element = WebDriverWait(self.browser, self.page_wait_time).until(
                EC.presence_of_element_located((By.NAME, "paperBill"))
            )
            element.click()
        except common.exceptions.TimeoutException:
            print "No paper bill button!"

        # Find pdf (how know if done?)
        num_to_try = 20
        pdfs = []
        while num_to_try > 0:
            print "Checking for download " + str(num_to_try)
            pdfs = glob.glob(os.path.join(self.download_dir, "*.pdf"))
            if len(pdfs) > 0:
                break
            else:
                num_to_try -= 1
                time.sleep(5)

        # If got, rename and move to right location
        newfilename = None
        amount = None
        if len(pdfs) == 0:
            print "Never got it!"
        elif len(pdfs) > 1:
            print "Uh-oh, some trash in temp dir!"
        else:
            time.sleep(5)  # make sure it finishes downloading

            # AT&T pdf files arent compliant (boo!), until can workaround, skip reading
            # pdf_file_obj = open(pdfs[0], 'rb')
            # pdf_reader = PyPDF2.PdfFileReader(pdf_file_obj)
            # pdf_reader.numPages
            # page_obj = pdf_reader.getPage(0)
            # raw_text = page_obj.extractText()
            # print raw_text
            # pdf_file_obj.close()
            #
            # att_amt_re = "Amount to be Debited\s*\$(\d*.\d\d)"
            # amt_stuff = re.search(att_amt_re, raw_text)
            # amount = amt_stuff.group(1)

            att_dnld_re = "(ATT)_\d*_(\d\d\d\d)(\d*).*(.pdf)"
            filestuff = re.search(att_dnld_re, pdfs[0])
            newfilename = filestuff.group(1) + "_" + filestuff.group(2) + "_" + filestuff.group(3) + ".pdf"
            print newfilename

        if newfilename:
            shutil.move(os.path.join(self.download_dir, pdfs[0]), os.path.join(att_dir, newfilename))
        else:
            print "Problem with AT&T bill"
        return amount

    def get_cox_bill(self):
        cox_dir = os.path.join(self.utes_base_dir, "CoxInternet")
        cox_login = {"userid": {"field_type": "id", "field_text": "userid", "input": self.pw_data["cox"][0]},
                     "pw": {"field_type": "id", "field_text": "user-password", "input": self.pw_data["cox"][1]},
                     "login_button": {"field_type": "name", "field_text": "signin-submit"}}
        self.browser.get("https://www.cox.com/ibill/sign-in.cox")
        self.login(cox_login)

        # Second page, wait for View Bill (PDF) and click
        try:
            element = WebDriverWait(self.browser, self.page_wait_time).until(
                EC.presence_of_element_located((By.LINK_TEXT, "View Bill (PDF)"))
            )
            element.click()
        except common.exceptions.TimeoutException:
            print "No bill history!"

        # Find pdf (how know if fully done?)
        num_to_try = 20
        pdfs = []
        while num_to_try > 0:
            print "Checking for download " + str(num_to_try)
            pdfs = glob.glob(os.path.join(self.download_dir, "*.stmt"))
            if len(pdfs) > 0:
                break
            else:
                num_to_try -= 1
                time.sleep(5)

        amount = None
        if len(pdfs) == 0:
            print "Never got it!"
        elif len(pdfs) > 1:
            print "Uh-oh, some trash in temp dir!"
        else:
            # get amount and date from pdf
            pdf_file_obj = open(pdfs[0], 'rb')
            pdf_reader = PyPDF2.PdfFileReader(pdf_file_obj)
            pdf_reader.numPages
            page_obj = pdf_reader.getPage(0)
            raw_text = page_obj.extractText()
            pdf_file_obj.close()

            cox_amt_re = "TOTAL DUE BY.*\$(\d*.\d\d)"
            amt_stuff = re.search(cox_amt_re, raw_text)
            amount = amt_stuff.group(1)

            cox_date_re = "ACCOUNT SUMMARY as of\s*(\S+)\s*\d+,\s*(\d*)"
            date_stuff = re.search(cox_date_re, raw_text)
            newfilename = "Cox_" + str(date_stuff.group(2)) + "-" + "{0:0>2}" + ".pdf"
            newfilename = newfilename.format(time.strptime(date_stuff.group(1),'%b').tm_mon)

        if newfilename:
            shutil.move(os.path.join(self.download_dir, pdfs[0]), os.path.join(cox_dir, newfilename))
        else:
            print "Problem with Cox bill"

        return amount

    def get_directv_bill(self):
        dtv_dir = os.path.join(self.utes_base_dir, "DirectTV")
        directv_login = {"userid": {"field_type": "id", "field_text": "loginField", "input": self.pw_data["directv"][0]},
                         "pw": {"field_type": "id", "field_text": "passwordField", "input": self.pw_data["directv"][1]},
                         "login_button": {"field_type": "link_text", "field_text": "Sign In to My Account"}}

        self.browser.get("https://www.directv.com/DTVAPP/login/login.jsp")
        self.login(directv_login)

        return 0.00


def main():
    # Run specific parameters
    utes_base_dir = r"E:\UsersBulk\user\Dropbox\HomeUtilities"  # "/Users/sullivak/Dropbox/HomeUtilities"
    csv_file = r"E:\UsersBulk\user\local.csv"
    bs = BillScraper(utes_base_dir, csv_file)

    # amt = bs.get_att_bill()
    # amt = bs.get_cox_bill()
    amt = bs.get_directv_bill()


if __name__ == "__main__":
    main()