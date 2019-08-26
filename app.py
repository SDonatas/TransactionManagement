from flask import g, Flask, render_template, request, url_for, flash, redirect, send_from_directory, session, abort
from werkzeug.utils import secure_filename
import sqlite3
import os
from zipfile import ZipFile 
from pandas_ods_reader import read_ods
import pandas as pd
import datetime
import logging
from functools import wraps
import math

#Path variable
try:
    script_path = os.path.dirname(os.path.abspath(__file__)) + "/"
except:
    script_path = ""

#SETUP LOGGING
logging.basicConfig(filename=script_path + 'TransactionImport.log',
                    level=logging.INFO,
                    format='%(asctime)s %(levelname)-8s %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')

#Initiate app
app = Flask(__name__)


DATABASE = script_path + 'setup.db'
DATABASE_TXN = script_path + 'data.db'
UPLOAD_FOLDER = script_path + 'uploads'
ALLOWED_EXTENSIONS = set(['xlsx', 'ods', 'csv'])
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.secret_key = ''

columns = ['MerchantName',
            'ClientName',
            'TransactionDate',
            'TransactionType',
            'DataEntryMethod',
            'CurrencyCode',
            'DccCurrencyCode',
            'SaleAmount',
            'DccAmount', 
            'CardNumber',
            'AuthMessage',
            'TerminalId',
            'CardScheme',
            'TransactionMode',
            'ExpiryDate',
            'ResponseCode',
            'UploadTime',
            'UploadId']



def get_db(DATABASE = DATABASE):
    db = getattr(g, '_setup', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_setup', None)
    if db is not None:
        db.close()

def query_db(query, args=(), one=False, insert=False, DATABASE = DATABASE):
    con = get_db(DATABASE)
    cur = con.execute(query, args)
    if insert == True:
        con.commit()
        rv = None
    else:
        rv = cur.fetchall()

    cur.close()
    return (rv[0] if rv else None) if one else rv

def createdDatabases():
    query_db('CREATE TABLE IF NOT EXISTS Merchants(name text);')
    query_db('CREATE TABLE IF NOT EXISTS CardSchemes(name text);')
    query_db('CREATE TABLE IF NOT EXISTS UploadHistory(uploadtime timestamp, filename text, success boolean, len numeric, UploadId numeric);', DATABASE = DATABASE_TXN)
    query_db('CREATE TABLE IF NOT EXISTS data(MerchantName text, ClientName text, TransactionDate timestamp, TransactionType text, DataEntryMethod text, CurrencyCode text, DccCurrencyCode text, SaleAmount real, DccAmount real, CardNumber text, AuthMessage text, TerminalId text, CardScheme text, TransactionMode text, ExpiryDate text, ResponseCode text, UploadTime timestamp, UploadId numeric);', DATABASE = DATABASE_TXN)
    #query_db('DROP TABLE exportHistory;', DATABASE = DATABASE_TXN, insert=True)
    query_db('CREATE TABLE IF NOT EXISTS exportHistory(exportDate timestamp, success boolean, len numeric, filename text, exportId numeric);', DATABASE = DATABASE_TXN)
    


@app.route('/login', methods=['POST'])
def do_admin_login():
    if request.form['password'] == '' and request.form['username'] == '':
        session['logged_in'] = True
    else:
        flash('wrong password!')
    
    return home()


@app.route('/logout', methods=['GET'])
def do_admin_logout():
    session['logged_in'] = False
    return home()


def LoggedinDecorator(f, *args, **kvargs):
    @wraps(f, *args, **kvargs)
    def wrapper(*args, **kvargs):
        if not session.get('logged_in'):
            return render_template('login.html')
        else:
            return f(*args, **kvargs)

    return wrapper

@app.route('/')
@LoggedinDecorator
def home():
    createdDatabases()
    return render_template('base.html', name=None)


@app.route('/report')
@LoggedinDecorator
def report():
    data = [x for x in query_db('Select * from data', DATABASE = DATABASE_TXN)]
    data = pd.DataFrame(data, columns=columns)
    if data.shape[0] == 0:
        return render_template('report.html', data={'No Data': [[]]}, Reportcolumns=[])
    else:
        try:
            os.remove(script_path + 'export/report.csv')
        except:
            pass
        #CardSchemes = [x[0] for x in query_db('Select * from CardSchemes')]
        CardSchemes = [x for x in data['CardScheme'].unique()]
        data['Year-Month'] = data['TransactionDate'].map(lambda x: pd.to_datetime(x).strftime("%Y-%m")) 
        data = data.groupby(['Year-Month', 'MerchantName', 'CardScheme']).agg({'TransactionDate': 'count', 'SaleAmount': 'sum'}).reset_index()
        years = [x for x in data['Year-Month'].unique()]
        years.sort()

        
        #print(data.head())
        #print(years)

        for card in CardSchemes:
            data[card] = data.apply(lambda x: x['TransactionDate'] if x['CardScheme'] == card else 0, axis=1)

        Reportcolumns = {'MerchantName': 'Merchant Name', 'TransactionDate': 'Total Count', 'SaleAmount': 'Sale Amount'}
        Reportcolumns = {**Reportcolumns, **{x:x for x in CardSchemes}}

        data = data.groupby(['Year-Month', 'MerchantName'])[[x for x in Reportcolumns.keys()]].sum().reset_index()

        payload = {}
        for year in years:
            payload[year] = data[data['Year-Month'] == year].drop(['Year-Month'], axis=1)[[x for x in Reportcolumns.keys()]]
            payload[year]['SaleAmount'] = payload[year]['SaleAmount'].round(2)
            payload[year] = payload[year].values.tolist()

        data['SaleAmount'] = data['SaleAmount'].round(2)
        data = data.rename(Reportcolumns, axis=1)
        data.to_csv(script_path + 'export/report.csv', index=False)

        return render_template('report.html', data=payload, Reportcolumns=[x for x in Reportcolumns.values()])

@app.route('/report/download')
@LoggedinDecorator
def reportDownload():
    try:
        return send_from_directory(directory=script_path + 'export/', filename='report.csv', as_attachment=True)
    except:
        flash("Error: Could not find report summary file")
        return render_template('report.html', data={'No Data': [[]]}, Reportcolumns=[])


@app.route('/merchants', methods=['GET', 'POST'])
@LoggedinDecorator
def merchants():
    submit = request.form.get("NewMerchant")
    delete = request.form.getlist("defaultCheck1")



    if submit != None and submit != "":
        query_db("""INSERT INTO Merchants (name) VALUES ('{}');""".format(submit), insert=True)


    if delete != None and delete != "":
        for item in delete:
            query_db("""DELETE FROM Merchants WHERE name = '{}';""".format(item), insert=True)


    Merchants = [x[0] for x in query_db('Select * from Merchants')]
    if len(Merchants) > 250:
        Currentpage = request.args.get('page')
        Currentpage = 0 if (Currentpage == None or Currentpage == "") else Currentpage
        totalPages = math.ceil(len(Merchants) / 250)
        Merchants = Merchants[250*int(Currentpage):250*int(Currentpage)+250]
        pageDic = {}
        for page in range(0, totalPages):
            pageDic[page] = '/merchants?page=' + str(page)


    else:
        pageDic = {}

    #print(Merchants)

    #print(submit)
    #print(request.form)
    return render_template('merch.html', Merchants=Merchants, pageDic = pageDic)



@app.route('/merchants/upload', methods=['POST'])
@LoggedinDecorator
def merchantsUpload(): 
    def allowed_file(filename):
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

    if request.method == 'POST':
        try:
            # check if the post request has the file part
            if 'file' not in request.files:
                flash('No file part')
                return redirect(url_for('merchants'))
            file = request.files['file']
            # if user does not select file, browser also
            # submit an empty part without filename
            if file.filename == '':
                flash('No selected file.')
                return redirect(url_for('merchants'))

            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename).strip().replace(" ", "_")

                #Save file
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

                if filename.split(".")[1] == 'xlsx':
                    df = pd.read_excel(script_path + "uploads/" + filename)
                  


                elif filename.split(".")[1] == 'ods':
                    #sheet_name = "sheet1"
                    print(script_path + 'uploads/' + filename)
                    df = read_ods(script_path + 'uploads/' + filename, 0)
                   

                elif filename.split(".")[1] == 'csv':
                    print(script_path + 'uploads/' + filename)
                    df = pd.read_csv(script_path + 'uploads/' + filename)
                


                else:
                    flash('Error: Bad file extension.')
                    return redirect(url_for('merchants'))


                os.remove(script_path + 'uploads/' + filename)

                #apply filtering
                Merchants = [x[0] for x in query_db('Select * from Merchants')]

                if ('MerchantName' not in df.columns):
                    flash('Could not find MerchantName column in the data')
                    return redirect(url_for('merchants'))

                df = [x for x in df['MerchantName'].unique() if x not in Merchants]

                if len(df) == 0:
                    flash('No new merchants found')
                    return redirect(url_for('merchants'))

                df = pd.DataFrame(df, columns=['name'])
                
                try:
                    df.to_sql('Merchants', index=False, if_exists = 'append', con=get_db(DATABASE = DATABASE))
                    logging.info("Successfully added merchants from file ({}) to a database".format(filename))
                    flash('Success. Added merchants from a file')

                except:
                    logging.info('Failed to add merchants from file ({}) to a database'.format(filename))
                    flash('Fail adding merchants from file')
                #Filtering
                #for row in df.iterrows():
                #    print(", ".join(["""'""" + str(row[x]) + """'""" for x in columns]))
                #    print("""INSERT INTO data ({}) VALUES ({});""".format(", ".join([x for x in columns]), ", ".join(["""'""" + row[x] + """'""" for x in columns])))
                #    query_db("""INSERT INTO data ({}) VALUES ({});""".format(", ".join([x for x in columns]), ", ".join(["""'""" + row[x] + """'""" for x in columns])), insert=True, DATABASE = DATABASE_TXN)



                #Uploading
                del df

                return redirect(url_for('merchants'))
        except:
            flash('Parsing error... Please contact donatas.svilpa@gmail.com, or try different file type')
            return redirect(url_for('merchants'))


        else:
            flash('Bad file extension.')
            return redirect(url_for('merchants'))






@app.route('/cardSchemes', methods=['GET', 'POST'])
@LoggedinDecorator
def cardSchemes():
    submit = request.form.get("NewCardScheme")
    delete = request.form.getlist("defaultCheck1")


    if submit != None and submit != "":
        query_db("""INSERT INTO CardSchemes (name) VALUES ('{}');""".format(submit), insert=True)


    if delete != None and delete != "":
        for item in delete:
            query_db("""DELETE FROM CardSchemes WHERE name = '{}';""".format(item), insert=True)


    CardSchemes = [x[0] for x in query_db('Select * from CardSchemes')]
    #print(Merchants)

    #print(submit)
    #print(request.form)
    return render_template('card.html', CardSchemes=CardSchemes)




@app.route("/export", methods=['GET', 'POST'])
@LoggedinDecorator
def export():

    submit = request.form.get("exportData")
    delete = request.form.getlist("defaultCheck1")
    #fileSelected = request.form.get("fileSelected")
    fileSelected = 'All'

    if delete != None and delete != "":
        for item in delete:
            exportFilesToBeRemoved = [x for x in query_db('Select * from exportHistory where exportId = {}'.format(item), DATABASE = DATABASE_TXN)]
            for file in exportFilesToBeRemoved:
                try:
                    os.remove(script_path + "export/" + file[3])
                    logging.info("Removed file {}".format(file))
                except:
                    logging.info("Removed file FAILED {}".format(file[3]))

            query_db("""DELETE FROM exportHistory WHERE exportId = '{}';""".format(item), insert=True, DATABASE = DATABASE_TXN)
            logging.info("Deleted from exportHistory file {}".format(file[3]))

    if submit != None and submit != "":
        try:
            exportTimestamp = datetime.datetime.now()
            files = []
            zipExportFile = "export_" + str(exportTimestamp) + ".zip"

            if fileSelected == "All":
                Txn = pd.DataFrame([x for x in query_db('Select * from data', DATABASE = DATABASE_TXN)], columns = columns)
            else:
                Txn = pd.DataFrame([x for x in query_db('Select * from data where UploadId = {}'.format(fileSelected), DATABASE = DATABASE_TXN)], columns = columns)

            Txn['TxnDate'] = Txn.apply(lambda x: pd.to_datetime(x['TransactionDate']).strftime("%Y-%m"), axis=1)
            RowLen = Txn.shape[0]

            #Save filess by merchant
            for merchant in Txn['MerchantName'].unique():
                for TxnDate in Txn[Txn['MerchantName'] == merchant]['TxnDate'].unique():
                    file_to_save_to = merchant + "_" + TxnDate + ".csv"
                    Txn[(Txn['MerchantName'] == merchant) & (Txn['TxnDate'] == TxnDate)].drop(['UploadTime', 'UploadId', 'TxnDate'], axis=1).to_csv(script_path + "export/" + file_to_save_to, index=False)
                    files.append({"filePath": script_path + "export/" + file_to_save_to, 'arcName': file_to_save_to})

            #Zip all files
            # writing files to a zipfile 
            with ZipFile(script_path + "export/" + zipExportFile,'w') as zip: 
                # writing each file one by one 
                for file in files: 
                    zip.write(file['filePath'], file['arcName']) 
            logging.info("Zip {} created".format(file['arcName']))
          

            #Remove old csvs and keep zip file
            for file in files:
                os.remove(file['filePath'])


            #Add line within export history
            #Get Max exportID if exist
            exportId = query_db('Select max(exportId) from exportHistory', DATABASE = DATABASE_TXN)
            exportId = 0 if exportId[0][0] == None else exportId[0][0] + 1

            query_db("""INSERT INTO exportHistory (exportDate, success, len, filename, exportId) VALUES ('{}', '{}', '{}', '{}', '{}');""".format(str(exportTimestamp), 'True', RowLen, zipExportFile, exportId), insert=True, DATABASE = DATABASE_TXN)
            logging.info("Export record generated")
            if fileSelected == "All":
                query_db("""DELETE FROM data;""" , insert=True, DATABASE = DATABASE_TXN)
                logging.info("All transaction data in local storage deleted")
                query_db("""DELETE FROM UploadHistory;""" , insert=True, DATABASE = DATABASE_TXN)
                logging.info("All data in UploadHistory deleted")
            else:
                query_db("""DELETE FROM data where UploadID = {};""".format(fileSelected) , insert=True, DATABASE = DATABASE_TXN)
                logging.info("All transaction data in local storage deleted from Upload fileId {}".format(fileSelected))
                query_db("""DELETE FROM UploadHistory where UploadId = {};""".format(fileSelected) , insert=True, DATABASE = DATABASE_TXN)
                logging.info("All data in UploadHistory deleted from upload fileID {}".format(fileSelected))



            flash('File exported successfully')
        except:
            logging.info('Export error')
            flash('Export error')

    exportHistory = [x for x in query_db('Select * from exportHistory', DATABASE = DATABASE_TXN)]

    #Import file list
    importHistory = [x for x in query_db('Select * from UploadHistory', DATABASE = DATABASE_TXN)]

    return render_template('export.html', exportHistory=exportHistory, importHistory=importHistory)


@app.route("/exportDownload")
@LoggedinDecorator
def exportDownload():
    file = request.args.get('file')
    print(script_path + 'export/' + file)

    #exportHistory = [x for x in query_db('Select * from exportHistory', DATABASE = DATABASE_TXN)]
    #return render_template('export.html', exportHistory=exportHistory)
    return send_from_directory(directory=script_path + 'export/', filename=file, as_attachment=True)




@app.route("/excel", methods=['GET', 'POST'])
@LoggedinDecorator
def excel():

    delete = request.form.getlist("defaultCheck1")

    if delete != None and delete != "":
        for item in delete:
            query_db("""DELETE FROM data WHERE UploadId = {};""".format(item), insert=True, DATABASE = DATABASE_TXN)
            query_db("""DELETE FROM UploadHistory WHERE UploadId = {};""".format(item), insert=True, DATABASE = DATABASE_TXN)



    History = [x for x in query_db('Select * from UploadHistory', DATABASE = DATABASE_TXN)]
    return render_template('excel.html', History=History)



@app.route("/ExcelUpload", methods=['POST'])
@LoggedinDecorator
def ExcelUpload():
    
    def allowed_file(filename):
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

    if request.method == 'POST':
        try:
            # check if the post request has the file part
            if 'file' not in request.files:
                flash('No file part')
                return redirect(url_for('excel'))
            file = request.files['file']
            # if user does not select file, browser also
            # submit an empty part without filename
            if file.filename == '':
                flash('No selected file.')
                return redirect(url_for('excel'))

            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename).strip().replace(" ", "_")

                #Save file
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

                if filename.split(".")[1] == 'xlsx':
                    df = pd.read_excel(script_path + "uploads/" + filename)
                  


                elif filename.split(".")[1] == 'ods':
                    #sheet_name = "sheet1"
                    print(script_path + 'uploads/' + filename)
                    df = read_ods(script_path + 'uploads/' + filename, 0)
                   

                elif filename.split(".")[1] == 'csv':
                    print(script_path + 'uploads/' + filename)
                    df = pd.read_csv(script_path + 'uploads/' + filename)
                


                else:
                    flash('Error: Bad file extension.')
                    return redirect(url_for('excel'))


                os.remove(script_path + 'uploads/' + filename)

                #apply filtering
                CardSchemes = [x[0] for x in query_db('Select * from CardSchemes')]
                Merchants = [x[0] for x in query_db('Select * from Merchants')]

                if ('MerchantName' not in df.columns) or ('CardScheme' not in df.columns):
                    flash('Could not find MerchantName or CardScheme columns in the data')
                    return redirect(url_for('excel'))

                df = df[df['MerchantName'].isin(Merchants)]
                df = df[df['CardScheme'].isin(CardSchemes)]


                if df.shape[0] == 0:
                    flash('No data to upload after applying filtering')
                    return redirect(url_for('excel'))

                #check if all columns exist, with tolerance for 2 missing
                assert len(columns) + 2 >= len([x for x in df.columns if x in columns]) and len(columns) >= len([x for x in df.columns if x in columns]) - 2

                #add empty columns
                for col in columns:
                    if col not in df.columns:
                        df[col] = None


                #df.to_sql('data', con=get_db(DATABASE = DATABASE_TXN))
                #UploadHistory(uploadtime timestamp, filename text, success boolean)

                #Set timestamp
                timestamp = datetime.datetime.now()
                df['UploadTime'] = str(timestamp)

                #Fix Datatime
                if filename.split(".")[1] == 'csv':
                    try:
                        df['TransactionDate'] = df['TransactionDate'].map(lambda x: pd.to_datetime(str(x), format="%d/%m/%Y %H:%M:%S"))
                    except:
                        df['TransactionDate'] = df['TransactionDate'].map(lambda x: pd.to_datetime(str(x), format="%d/%m/%Y %H:%M"))
                elif filename.split(".")[1] == 'ods':
                    try:
                        df['TransactionDate'] = df['TransactionDate'].map(lambda x: pd.to_datetime(str(x), format="%Y/%m/%dT%H:%M:%S"))
                    except:
                        df['TransactionDate'] = df['TransactionDate'].map(lambda x: pd.to_datetime(str(x), format="%Y/%m/%dT%H:%M"))
                elif filename.split(".")[1] == 'xlsx':
                    try:
                        df['TransactionDate'] = df['TransactionDate'].map(lambda x: pd.to_datetime(str(x), format="%Y/%m/%d %H:%M:%S"))
                    except:
                        df['TransactionDate'] = df['TransactionDate'].map(lambda x: pd.to_datetime(str(x), format="%Y/%m/%d %H:%M"))


                #Make sure Sale Amount is proper float, as it might come with semicolons from excel file

                df['SaleAmount'] = df['SaleAmount'].map(lambda x: x.replace(",", ".") if type(x) == str else x)
                df['SaleAmount'] = df['SaleAmount'].astype(float)
               



                #Set Upload id
                UploadId = query_db('Select max(UploadId) from UploadHistory', DATABASE = DATABASE_TXN)
                UploadId = 0 if UploadId[0][0] == None else UploadId[0][0] + 1
                df['UploadId'] = UploadId
             
                
                try:
                    df.to_sql('data', index=False, if_exists = 'append', con=get_db(DATABASE = DATABASE_TXN))
                    query_db("""INSERT INTO UploadHistory (uploadtime, filename, success, len, UploadId) VALUES ('{}', '{}', '{}', '{}', '{}');""".format(str(timestamp), filename, "True", str(df.shape[0]), UploadId), DATABASE=DATABASE_TXN, insert=True)
                    logging.info("Successfully uploaded file ({}) contents to a database".format(filename))
                    flash('Success')

                except:
                    query_db("""INSERT INTO UploadHistory (uploadtime, filename, success, len, UploadId) VALUES ('{}', '{}', '{}', '{}', '{}');""".format(str(timestamp), filename, "False", str(df.shape[0]), UploadId), DATABASE=DATABASE_TXN, insert=True)
                    logging.info('Failed to upload data from file ({}) to a database'.format(filename))
                    flash('Fail')
                #Filtering
                #for row in df.iterrows():
                #    print(", ".join(["""'""" + str(row[x]) + """'""" for x in columns]))
                #    print("""INSERT INTO data ({}) VALUES ({});""".format(", ".join([x for x in columns]), ", ".join(["""'""" + row[x] + """'""" for x in columns])))
                #    query_db("""INSERT INTO data ({}) VALUES ({});""".format(", ".join([x for x in columns]), ", ".join(["""'""" + row[x] + """'""" for x in columns])), insert=True, DATABASE = DATABASE_TXN)



                #Uploading
                return redirect(url_for('excel'))
        except:
            flash('Parsing error... Please contact donatas.svilpa@gmail.com, or try different file type')
            return redirect(url_for('excel'))


        else:
            flash('Bad file extension.')
            return redirect(url_for('excel'))




if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0")