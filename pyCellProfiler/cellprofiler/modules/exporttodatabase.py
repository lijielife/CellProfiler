'''<b>ExportToDatabase:</b>  Exports data directly to a database, or in database readable format, including an importing file
with column names and a CellProfiler Analyst properties file, if desired.
<hr>

This module exports measurements directly to a database, or to a SQL compatible format. 
It allows you to create MySQL and associated data files which will create a
database and import the data into it and gives you the option of creating
a properties file for use with CellProfiler Analyst. Optionally, you can create
an SQLite DB file if you do not have a server on which to run MySQL.
 
This module must be run at the end of a pipeline, or second to last if 
you are using the CreateBatchFiles module. If you forget this module, you
can also run the ExportDatabase data tool after processing is complete; 
its functionality is the same.

The database is set up with two primary tables. These tables are the
Per_Image table and the Per_Object table (which may have a prefix if you
specify). The Per_Image table consists of all the Image measurements and
the Mean and Standard Deviation of the object measurements. There is one
Per_Image row for every image. The Per_Object table contains all the
measurements for individual objects. There is one row of object
measurements per object identified. The two tables are connected with the
primary key column ImageNumber. The Per_Object table has another primary
key called ObjectNumber, which is unique per image.

Oracle is not currently supported; you can create your own Oracle DB using
the .csv output option, and writing a simple script to upload to the DB.


'''
#CellProfiler is distributed under the GNU General Public License.
#See the accompanying file LICENSE for details.
#
#Developed by the Broad Institute
#Copyright 2003-2009
#
#Please see the AUTHORS file for credits.
#
#Website: http://www.cellprofiler.org

__version__="$Revision$"

import csv
import datetime
import numpy as np
import os
import random
import re
import sys
try:
    import MySQLdb
    from MySQLdb.cursors import SSCursor
    HAS_MYSQL_DB=True
except:
    sys.stderr.write("WARNING: MySQL direct insert can't run within MySQLdb package")

import cellprofiler.cpmodule as cpm
import cellprofiler.settings as cps
import cellprofiler.preferences as cpp
import cellprofiler.measurements as cpmeas

DB_MYSQL = "MySQL"
DB_ORACLE = "Oracle"
DB_SQLITE = "SQLite"

def execute(cursor, query, return_result=True):
    print query
    cursor.execute(query)
    if return_result:
        return get_results_as_list(cursor)

def get_results_as_list(cursor):
    r = get_next_result(cursor)
    l = []
    while r:
        l.append(r)
        r = get_next_result(cursor)
    return l

def get_next_result(cursor):
    try:
        return cursor.next()
    except MySQLdb.Error, e:
        raise DBException, 'Error retrieving next result from database: %s'%(e)
        return None
    except StopIteration, e:
        return None
    
def connect_mysql(host, user, pw, db):
    '''Creates and returns a db connection and cursor.'''
    connection = MySQLdb.connect(host=host, user=user, passwd=pw, db=db)
    cursor = SSCursor(connection)
    return connection, cursor

def connect_sqlite(db_file):
    '''Creates and returns a db connection and cursor.'''
    from pysqlite2 import dbapi2 as sqlite
    connection = sqlite.connect(db_file)
    cursor = connection.cursor()
    return connection, cursor

    
    
class ExportToDatabase(cpm.CPModule):
 
    variable_revision_number = 8
    category = "File Processing"

    def create_settings(self):
        self.module_name = "ExportToDatabase"
        self.db_type = cps.Choice("What type of database do you want to use?",
                                  [DB_MYSQL,DB_ORACLE,DB_SQLITE], DB_MYSQL, doc = '''<ul><li><i>MySQL</i>
                                  will allow you to write directly to the database.  <li><i>Oracle</i> is currently
                                  not supported, but writing your data to .csv files will allow you to upload your
                                  data to an Oracle database with a simple script. <li><i>SQLite</i> will write 
                                  sqlite files directly.  More information about sqlite can be found at <a href="http://www.sqlite.org/"> http://www.sqlite.org/</a> </ul>''')
        self.db_name = cps.Text(
            "What is the name of the database you want to use?", "DefaultDB")
        self.want_table_prefix = cps.Binary(
            "Do you want to add a prefix to your table names?", False, doc = '''This gives you the option to append text to your table names
            (Per_Image and Per_Object).  CellProfiler will warn you before overwriting an existing table.''')
        self.table_prefix = cps.Text(
            "What is the table prefix you want to use?", "Expt_")
        self.sql_file_prefix = cps.Text(
            "What prefix do you want to use to name the SQL file?", "SQL_")
        self.use_default_output_directory = cps.Binary(
            "Do you want to save files in the default output directory?", True)
        self.output_directory = cps.Text(
            "What directory should be used to save files?", ".")
        self.save_cpa_properties = cps.Binary(
            "Do you want to create a CellProfilerAnalyst properties file?", 
            False, doc = '''Generate a template
            properties for using your new database in CellProfiler Analyst (a data
            exploration tool which can also be downloaded from
            <a href="http://www.cellprofiler.org/"> http://www.cellprofiler.org/ </a>). The module will attempt to fill in as many as the entries as possible 
            based on the current handles structure. However, entries such as the 
            server name, username and password are omitted. Hence, opening the 
            properties file in CPA will produce an error since it won't be able to
            connect to the server. However, you can still edit the file in CPA and
            then fill in the required information.''')
        self.store_csvs = cps.Binary(
            "Store the database in CSV files? ", False, doc = '''This will write per_image and 
            per_object tables as a series of CSV files along with an SQL file 
            that can be used with those files to create the database.  You can also look at the csv
            files in a spreadsheet program, such as Excel.''')
        self.db_host = cps.Text("What is the database host?", "imgdb01")
        self.db_user = cps.Text("What is the database username?", "cpuser")
        self.db_passwd = cps.Text("What is the database password?", "cPus3r")
        self.sqlite_file = cps.Text(
            "What is the SQLite database file you want to write to?", 
            "DefaultDB.db")
        self.wants_agg_mean = cps.Binary(
            "Do you want to calculate the aggregate mean value of each "
            "object measurement per image?", True, doc = '''ExportToDatabase can calculate statistics over all the objects in each image
            and store the results as columns in the database. For instance, if
            you are measuring the area of the Nuclei objects and you check the aggregate
            mean box in this module, ExportToDatabase will create a column in the Per_Image
            table called Mean_Nuclei_AreaShape_Area. You may not want to use 
            ExportToDatabase to calculate these measurements if your pipeline generates
            a large number of per-object measurements; doing so might exceed database
            column limits. These columns can be created manually for selected measurements.
            For instance, the following SQL creates the Mean_Nuclei_AreaShape_Area column:
            
                ALTER TABLE Per_Image ADD (Mean_Nuclei_AreaShape_Area);
                UPDATE Per_Image SET Mean_Nuclei_AreaShape_Area = 
                    (SELECT AVG(Nuclei_AreaShape_Area)
                     FROM Per_Object
                     WHERE Per_Image.ImageNumber = Per_Object.ImageNumber);''')
        self.wants_agg_median = cps.Binary(
            "Do you want to calculate the aggregate median value of each "
            "object measurement per image?", False)
        self.wants_agg_std_dev = cps.Binary(
            "Do you want to calculate the standard deviation of the values "
            "of each object measurement per image?", False)
    
    def visible_settings(self):
        needs_default_output_directory =\
            (self.db_type != DB_MYSQL or self.store_csvs.value or
             self.save_cpa_properties.value)
        result = [self.db_type]
        if self.db_type==DB_MYSQL:
            if HAS_MYSQL_DB:
                result += [self.store_csvs]
            if self.store_csvs.value:
                result += [self.sql_file_prefix]
                result += [self.db_name]
            else:
                result += [self.db_name]
                result += [self.db_host]
                result += [self.db_user]
                result += [self.db_passwd]
        elif self.db_type==DB_SQLITE:
            result += [self.sqlite_file]
        elif self.db_type==DB_ORACLE:
            result += [self.sql_file_prefix]
        result += [self.want_table_prefix]
        if self.want_table_prefix.value:
            result += [self.table_prefix]
        result += [self.save_cpa_properties]
        if needs_default_output_directory:
            result += [self.use_default_output_directory]
            if not self.use_default_output_directory.value:
                result += [self.output_directory]
        result += [self.wants_agg_mean, self.wants_agg_median,
                   self.wants_agg_std_dev]

        return result
    
    def settings(self):
        return [self.db_type, self.db_name, self.want_table_prefix,
                self.table_prefix, self.sql_file_prefix, 
                self.use_default_output_directory, self.output_directory,
                self.save_cpa_properties, self.store_csvs, self.db_host, 
                self.db_user, self.db_passwd, self.sqlite_file,
                self.wants_agg_mean, self.wants_agg_median,
                self.wants_agg_std_dev]
    
    def backwards_compatibilize(self,setting_values,variable_revision_number,
                                module_name, from_matlab):
        if from_matlab and variable_revision_number == 6:
            new_setting_values = [setting_values[0],setting_values[1]]
            if setting_values[2] == cps.DO_NOT_USE:
                new_setting_values.append(cps.NO)
                new_setting_values.append("Expt_")
            else:
                new_setting_values.append(cps.YES)
                new_setting_values.append(setting_values[2])
            new_setting_values.append(setting_values[3])
            if setting_values[4] == '.':
                new_setting_values.append(cps.YES)
                new_setting_values.append(setting_values[4])
            else:
                new_setting_values.append(cps.NO)
                new_setting_values.append(setting_values[4])
            if setting_values[5][:3]==cps.YES:
                new_setting_values.append(cps.YES)
            else:
                new_setting_values.append(cps.NO)
            from_matlab = False
            setting_values = new_setting_values
            
        if (not from_matlab) and variable_revision_number == 6:
            # Append default values for store_csvs, db_host, db_user, 
            #  db_passwd, and sqlite_file to update to revision 7 
            new_setting_values = settings_values
            new_setting_values += [False, 'imgdb01', 'cpuser', '', 'DefaultDB.db']
            variable_revision_number = 7
        
        if (not from_matlab) and variable_revision_number == 7:
            # Added ability to selectively turn on aggregate measurements
            # which were all automatically calculated in version 7
            new_setting_values = setting_values + [True, True, True]
            variable_revision_number = 8
            
        return setting_values, variable_revision_number, from_matlab
    
    def test_valid(self,pipeline):
        if self.want_table_prefix.value:
            if not re.match("^[A-Za-z][A-Za-z0-9_]+$",self.table_prefix.value):
                raise cps.ValidationError("Invalid table prefix",self.table_prefix)

        if self.db_type==DB_MYSQL:
            if not re.match("^[A-Za-z0-9_]+$",self.db_name.value):
                raise cps.ValidationError("The database name has invalid characters",self.db_name)
        elif self.db_type==DB_SQLITE:
            if not re.match("^[A-Za-z0-9_].*$",self.sqlite_file.value):
                raise cps.ValidationError("The sqlite file name has invalid characters",self.sqlite_file)

        if not self.store_csvs.value:
            if not re.match("^[A-Za-z0-9_]+$",self.db_user.value):
                raise cps.ValidationError("The database user name has invalid characters",self.db_user)
            if not re.match("^[A-Za-z0-9_].*$",self.db_host.value):
                raise cps.ValidationError("The database host name has invalid characters",self.db_host)
        else:
            if not re.match("^[A-Za-z][A-Za-z0-9_]+$", self.sql_file_prefix.value):
                raise cps.ValidationError('Invalid SQL file prefix', self.sql_file_prefix)
            
    def prepare_run(self, pipeline, image_set_list, frame):
        if self.db_type == DB_ORACLE:
            raise NotImplementedError("Writing to an Oracle database is not yet supported")
        if not self.store_csvs.value:
            if self.db_type==DB_MYSQL:
                self.connection, self.cursor = connect_mysql(self.db_host.value, 
                                                             self.db_user.value, 
                                                             self.db_passwd.value,
                                                             self.db_name.value)
            elif self.db_type==DB_SQLITE:
                db_file = self.get_output_directory()+'/'+self.sqlite_file.value
                self.connection, self.cursor = connect_sqlite(db_file)
            try:
                object_table = self.get_table_prefix()+'Per_Object'
                image_table = self.get_table_prefix()+'Per_Image'
                r = execute(self.cursor, 'SELECT * FROM %s LIMIT 1'%(image_table))
                r = execute(self.cursor, 'SELECT * FROM %s LIMIT 1'%(object_table))
                import wx
                dlg = wx.MessageDialog(frame, 'ExportToDatabase will overwrite your tables "%s" and "%s". OK?'%(image_table, object_table),
                                    'Overwrite per_image and per_object table?', style=wx.OK|wx.CANCEL|wx.ICON_QUESTION)
                if dlg.ShowModal() != wx.ID_OK:
                    return False
            except:
                pass
            self.create_database_tables(self.cursor, 
                                        pipeline.get_measurement_columns(),
                                        not pipeline.in_batch_mode())
        return True
    
    def prepare_to_create_batch(self, pipeline, image_set_list, fn_alter_path):
        '''Alter the output directory path for the remote batch host'''
        self.output_directory.value = fn_alter_path(self.output_directory.value)
            
    def run(self, workspace):
        if ((self.db_type == DB_MYSQL and not self.store_csvs.value) or
            self.db_type == DB_SQLITE):
            mappings = self.get_column_name_mappings(workspace)
            self.write_data_to_db(workspace, mappings)
            
    def post_run(self, workspace):
        if self.save_cpa_properties.value:
            self.write_properties(workspace)
        if not self.store_csvs.value:
            # commit changes to db here or in run?
            print 'Commit'
            self.connection.commit()
            return
        mappings = self.get_column_name_mappings(workspace)
        if self.db_type == DB_MYSQL:
            per_image, per_object = self.write_mysql_table_defs(workspace, mappings)
        else:
            per_image, per_object = self.write_oracle_table_defs(workspace, mappings)
        self.write_data(workspace, mappings, per_image, per_object)
    
    def should_stop_writing_measurements(self):
        '''All subsequent modules should not write measurements'''
        return True
    
    def ignore_object(self,object_name):
        """Ignore objects (other than 'Image') if this returns true"""
        if object_name in ('Experiment','Neighbors'):
            return True
        
    def ignore_feature(self, object_name, feature_name, measurements=None):
        """Return true if we should ignore a feature"""
        if (self.ignore_object(object_name) or 
            feature_name.startswith('Description_') or 
            feature_name.startswith('ModuleError_') or 
            feature_name.startswith('TimeElapsed_') or 
            feature_name.startswith('ExecutionTime_')
            ):
            return True
        return False
    
    def get_column_name_mappings(self,workspace):
        """Scan all the feature names in the measurements, creating column names"""
        measurements = workspace.measurements
        mappings = ColumnNameMapping()
        for object_name in measurements.get_object_names():
            for feature_name in measurements.get_feature_names(object_name):
                if self.ignore_feature(object_name, feature_name, measurements):
                    continue
                mappings.add("%s_%s"%(object_name,feature_name))
                if object_name != 'Image':
                    for agg_name in cpmeas.AGG_NAMES:
                        mappings.add('%s_%s_%s'%(agg_name, object_name, feature_name))
        return mappings
    
    @property
    def agg_names(self):
        '''The list of selected aggregate names'''
        return [name
                for name, setting
                in ((cpmeas.AGG_MEAN, self.wants_agg_mean),
                    (cpmeas.AGG_MEDIAN, self.wants_agg_median),
                    (cpmeas.AGG_STD_DEV, self.wants_agg_std_dev))
                if setting.value]
    #
    # Create per_image and per_object tables in MySQL
    #
    def create_database_tables(self, cursor, column_defs, create_database):
        '''Creates empty image and object tables
        
        Creates the MySQL database (if MySQL), drops existing tables of the
        same name and creates the tables. Also initializes image_col_order,
        object_col_order and col_dict.
        
        cursor - database cursor for creating the tables
        column_defs - column definitions as returned by get_measurement_columns
        create_database - True to actually create the database, False if
                          we have to call this just to do the initialization
                          of image_col_order etc. during batch mode
        '''
        self.image_col_order = {}
        self.object_col_order = {}
        
        object_table = self.get_table_prefix()+'Per_Object'
        image_table = self.get_table_prefix()+'Per_Image'
        
        # Build a dictionary keyed by object type of measurement cols
        self.col_dict = {}
        for c in column_defs:
            if c[0]!=cpmeas.EXPERIMENT:
                if c[0] in self.col_dict.keys():
                    self.col_dict[c[0]] += [c]
                else:
                    self.col_dict[c[0]] = [c]
        
        # Create the database
        if self.db_type==DB_MYSQL and create_database:
            execute(cursor, 'CREATE DATABASE IF NOT EXISTS %s'%(self.db_name.value))
        execute(cursor, 'USE %s'% self.db_name.value)
        
        # Object table
        ob_tables = set([obname for obname, _, _ in column_defs 
                         if obname!=cpmeas.IMAGE and obname!=cpmeas.EXPERIMENT])
        statement = 'CREATE TABLE '+object_table+' (\n'
        statement += 'ImageNumber INTEGER,\n'
        statement += 'ObjectNumber INTEGER'
        agg_column_defs = []
        c = 2
        for ob_table in ob_tables:
            for obname, feature, ftype in column_defs:
                if obname==ob_table and not self.ignore_feature(obname, feature):
                    feature_name = '%s_%s'%(obname, feature)
                    # create per_image aggregate column defs 
                    for aggname in self.agg_names:
                        agg_column_defs += [(cpmeas.IMAGE,
                                             '%s_%s'%(aggname,feature_name),
                                             cpmeas.COLTYPE_FLOAT)]
                    self.object_col_order[feature_name] = c
                    c+=1
                    statement += ',\n%s %s'%(feature_name, ftype)
        statement += ',\nPRIMARY KEY (ImageNumber, ObjectNumber) )'
        
        if create_database:
            execute(cursor, 'DROP TABLE IF EXISTS %s'%(object_table))
            execute(cursor, statement)
        
        # Image table
        statement = 'CREATE TABLE '+image_table+' (\n'
        statement += 'ImageNumber INTEGER'
        c = 1
        for obname, feature, ftype in column_defs+agg_column_defs:
            if obname==cpmeas.IMAGE and not self.ignore_feature(obname, feature):
                if feature not in [d[1] for d in agg_column_defs]:
                    feature_name = '%s_%s'%(obname, feature)
                else:
                    feature_name = feature
                self.image_col_order[feature_name] = c
                statement += ',\n%s %s'%(feature_name, ftype)
                c+=1
        statement += ',\nPRIMARY KEY (ImageNumber) )'

        if create_database:
            execute(cursor, 'DROP TABLE IF EXISTS %s'%(image_table))
            execute(cursor, statement)
            print 'Commit'
            cursor.connection.commit()
    
    def write_mysql_table_defs(self, workspace, mappings):
        """Returns dictionaries mapping per-image and per-object column names to column #s"""
        
        m_cols = workspace.pipeline.get_measurement_columns()
        
        per_image = {"ImageNumber":0}
        per_object = {"ImageNumber":0,"ObjectNumber":1}
        per_image_idx = 1
        per_object_idx = 2
        measurements = workspace.measurements
        file_name_width, path_name_width = self.get_file_path_width(workspace)
        metadata_name_width = 128
        file_name = "%s_SETUP.SQL"%(self.sql_file_prefix)
        path_name = os.path.join(self.get_output_directory(), file_name)
        fid = open(path_name,"wt")
        fid.write("CREATE DATABASE IF NOT EXISTS %s;\n"%(self.db_name.value))
        fid.write("USE %s;\n"%(self.db_name.value))
        fid.write("CREATE TABLE %sPer_Image (ImageNumber INTEGER PRIMARY KEY"%
                  (self.get_table_prefix()))
        for object_name, feature, coltype in m_cols:
            if object_name != cpmeas.IMAGE:
                continue
            if self.ignore_feature(object_name, feature, measurements):
                continue
            feature_name = "%s_%s"%(object_name,feature)
            colname = mappings[feature_name]
            if coltype.upper() == 'FLOAT':
                coltype = 'FLOAT NOT NULL'
            fid.write(",\n%s %s"%(colname, coltype))
            per_image[feature_name] = per_image_idx
            per_image_idx += 1
        #
        # Put mean and std dev measurements for objects in the per_image table
        #
        for aggname in self.agg_names:
            for object_name in workspace.measurements.get_object_names():
                if object_name == 'Image':
                    continue
                for feature in measurements.get_feature_names(object_name):
                    if self.ignore_feature(object_name, feature, measurements):
                        continue
                    feature_name = "%s_%s_%s"%(aggname,object_name,feature)
                    colname = mappings[feature_name]
                    fid.write(",\n%s FLOAT NOT NULL"%(colname))
                    per_image[feature_name] = per_image_idx
                    per_image_idx += 1
        fid.write(");\n\n")
        #
        # Write out the per-object table
        #
        fid.write("""CREATE TABLE %sPer_Object(
ImageNumber INTEGER,
ObjectNumber INTEGER"""%(self.get_table_prefix()))
        for object_name in workspace.measurements.get_object_names():
            if object_name == 'Image':
                continue
            for feature in measurements.get_feature_names(object_name):
                if self.ignore_feature(object_name, feature, measurements):
                    continue
                feature_name = '%s_%s'%(object_name,feature)
                fid.write(",\n%s FLOAT NOT NULL"%(mappings[feature_name]))
                per_object[feature_name]=per_object_idx
                per_object_idx += 1
        fid.write(""",
PRIMARY KEY (ImageNumber, ObjectNumber));

LOAD DATA LOCAL INFILE '%s_image.CSV' REPLACE INTO TABLE %sPer_Image 
FIELDS TERMINATED BY ',' 
OPTIONALLY ENCLOSED BY '"' ESCAPED BY '\\\\';

LOAD DATA LOCAL INFILE '%s_object.CSV' REPLACE INTO TABLE %sPer_Object 
FIELDS TERMINATED BY ',' 
OPTIONALLY ENCLOSED BY '"' ESCAPED BY '\\\\';
"""%(self.base_name(workspace),self.get_table_prefix(),
     self.base_name(workspace),self.get_table_prefix()))
        fid.close()
        return per_image, per_object
    
    def write_oracle_table_defs(self, workspace, mappings):
        raise NotImplementedError("Writing to an Oracle database is not yet supported")
    
    def base_name(self,workspace):
        """The base for the output file name"""
        m = workspace.measurements
        first = m.image_set_start_number
        last = m.image_set_number + 1
        return '%s%d_%d'%(self.sql_file_prefix, first, last)
    
    
#    def write_data(self, workspace, mappings, per_image, per_object):
#        """Write the data in the measurements out to the csv files
#        workspace - contains the measurements
#        mappings  - map a feature name to a column name
#        per_image - map a feature name to its column index in the per_image table
#        per_object - map a feature name to its column index in the per_object table
#        """
#        measurements = workspace.measurements
#        image_filename = os.path.join(self.get_output_directory(),
#                                      '%s_image.CSV'%(self.base_name(workspace)))
#        object_filename = os.path.join(self.get_output_directory(),
#                                       '%s_object.CSV'%(self.base_name(workspace)))
#        fid_per_image = open(image_filename,"wt")
#        csv_per_image = csv.writer(fid_per_image)
#        fid_per_object = open(object_filename,"wt")
#        csv_per_object = csv.writer(fid_per_object)
#        
#        per_image_cols = max(per_image.values())+1
#        per_object_cols = max(per_object.values())+1
#        
#        image_rows, object_rows = self.get_measurement_rows(measurements, per_image, per_object)
#        
#        print 'write data'
#        print image_rows
#        print object_rows
#        
#        for row in image_rows:
#            csv_per_image.writerow(row)
#        for row in object_rows:
#            csv_per_object.writerow(row)
#        
#        fid_per_image.close()
#        fid_per_object.close()
        
        
        
    def write_data(self, workspace, mappings, per_image, per_object):
        """Write the data in the measurements out to the csv files
        workspace - contains the measurements
        mappings  - map a feature name to a column name
        per_image - map a feature name to its column index in the per_image table
        per_object - map a feature name to its column index in the per_object table
        """
        measurements = workspace.measurements
        image_filename = os.path.join(self.get_output_directory(),
                                      '%s_image.CSV'%(self.base_name(workspace)))
        object_filename = os.path.join(self.get_output_directory(),
                                       '%s_object.CSV'%(self.base_name(workspace)))
        fid_per_image = open(image_filename,"wt")
        csv_per_image = csv.writer(fid_per_image, quoting=csv.QUOTE_NONNUMERIC)
        fid_per_object = open(object_filename,"wt")
        csv_per_object = csv.writer(fid_per_object)
        
        per_image_cols = max(per_image.values())+1
        per_object_cols = max(per_object.values())+1
        for i in range(measurements.image_set_index+1):
            # Loop once per image set
            image_row = [None for k in range(per_image_cols)]
            image_number = i+measurements.image_set_start_number
            image_row[per_image['ImageNumber']] = image_number
            #
            # Fill in the image table
            #
            #
            # The individual feature measurements
            #
            max_count = 0
            for feature in measurements.get_feature_names('Image'):
                if self.ignore_feature('Image', feature, measurements):
                    continue
                feature_name = "%s_%s"%('Image',feature)
                value = measurements.get_measurement('Image',feature, i)
                if isinstance(value, np.ndarray):
                    value=value[0]
                if isinstance(value, unicode) or isinstance(value, str):
                    value = MySQLdb.escape_string(value)
                image_row[per_image[feature_name]] = value
                if feature_name.find('Count') != -1:
                    max_count = max(max_count,int(value))
            if max_count == 0:
                for object_name in measurements.get_object_names():
                    if object_name == 'Image':
                        continue
                    for feature in measurements.get_feature_names(object_name):
                        if self.ignore_feature(object_name, feature, measurements):
                            continue
                        for agg_name in self.agg_names:
                            feature_name = "%s_%s_%s"%(agg_name,object_name, feature)
                            image_row[per_image[feature_name]] = 0
            else:
                #
                # The aggregate measurements
                #
                agg_dict = measurements.compute_aggregate_measurements(
                    i, self.agg_names)
                for feature_name in agg_dict.keys():
                    image_row[per_image[feature_name]] = agg_dict[feature_name]
                #
                # Allocate an array for the per_object values
                #
                object_rows = np.zeros((max_count,per_object_cols))
                object_rows[:,per_object['ImageNumber']] = image_number
                object_rows[:,per_object['ObjectNumber']] = np.array(range(max_count))+1
                #
                # Loop through the objects, collecting their values
                #
                for object_name in measurements.get_object_names():
                    if object_name == 'Image':
                        continue
                    for feature in measurements.get_feature_names(object_name):
                        if self.ignore_feature(object_name, feature, measurements):
                            continue
                        feature_name = "%s_%s"%(object_name, feature)
                        values = measurements.get_measurement(object_name, feature, i)
                        values[np.logical_not(np.isfinite(values))] = 0
                        nvalues = np.product(values.shape)
                        if (nvalues < max_count):
                            sys.stderr.write("Warning: too few measurements for %s in image set #%d, got %d, expected %d\n"%(feature_name,image_number,nvalues,max_count))
                        elif nvalues > max_count:
                            sys.stderr.write("Warning: too many measurements for %s in image set #%d, got %d, expected %d\n"%(feature_name,image_number,nvalues,max_count))
                            values = values[:max_count]
                        object_rows[:nvalues,per_object[feature_name]] = values
                for row in range(max_count):
                    csv_per_object.writerow(object_rows[row,:])
            csv_per_image.writerow(image_row)
        fid_per_image.close()
        fid_per_object.close()
        
        
    def write_data_to_db(self, workspace, mappings):
        """Write the data in the measurements out to the database
        workspace - contains the measurements
        mappings  - map a feature name to a column name
        """
        measurements = workspace.measurements
        measurement_cols = workspace.pipeline.get_measurement_columns()
        index = measurements.image_set_index
        
        # TODO:
        # Check that all image and object columns reported by 
        #  get_measurement_columns agree with measurements.get_feature_names
#        for obname, col in self.col_dict.items():
#            f1 = measurements.get_feature_names(obname)
#            f2 = [c[1] for c in self.col_dict[obname]]
#            diff = set(f1).difference(set(f2))
#            assert not diff, 'The following columns were returned by measurements.get_feature_names and not pipeline.get_measurements: \n %s'%(diff)
#            diff = set(f2).difference(set(f1))
#            assert not diff, 'The following columns were returned by pipeline.get_measurements and not measurements.get_feature_names: \n %s'%(diff)
        
        # Fill image row with non-aggregate cols    
        max_count = 0
        image_number = index + measurements.image_set_start_number
        image_row = [None for k in range(len(self.image_col_order)+1)]
        image_row[0] = (image_number, cpmeas.COLTYPE_INTEGER, 'ImageNumber')
        if cpmeas.IMAGE in self.col_dict.keys():
            for m_col in self.col_dict[cpmeas.IMAGE]:
                feature_name = "%s_%s"%(cpmeas.IMAGE, m_col[1])
                value = measurements.get_measurement(cpmeas.IMAGE, m_col[1], index)
                if isinstance(value, np.ndarray):
                    value=value[0]
                if isinstance(value, float) and not np.isfinite(value):
                    value = 0
                if feature_name in self.image_col_order.keys():
                    image_row[self.image_col_order[feature_name]] =\
                             (value, m_col[2], feature_name)
                    if feature_name.find('Count') != -1:
                        max_count = max(max_count,int(value))
        
        # The object columns in order
        object_cols = (['ImageNumber','ObjectNumber'] + 
                       [ None] * len(self.object_col_order))
        for key in self.object_col_order.keys():
            object_cols[self.object_col_order[key]] = key

        if max_count == 0:
            for obname, cols in self.col_dict.items():
                if obname==cpmeas.IMAGE:
                    continue
                for col in cols:
                    for agg_name in self.agg_names:
                        feature_name = "%s_%s_%s"%(agg_name, obname, col[1])
                        if feature_name in self.image_col_order.keys():
                            image_row[self.image_col_order[feature_name]] =\
                                     (0, cpmeas.COLTYPE_FLOAT, feature_name)
            object_rows = []
        else:    
            # Compute and insert the aggregate measurements
            agg_dict = measurements.compute_aggregate_measurements(
                index, self.agg_names)
            for feature_name, value in agg_dict.items():
                if feature_name in self.image_col_order.keys():
                    image_row[self.image_col_order[feature_name]] =\
                             (value, cpmeas.COLTYPE_FLOAT, feature_name)
            
            object_rows = np.zeros((max_count, len(self.object_col_order)+2), dtype=object)
            for i in xrange(max_count):
                object_rows[i,0] = (image_number, cpmeas.COLTYPE_INTEGER)
                object_rows[i,1] = (i+1, cpmeas.COLTYPE_INTEGER)

            # Loop through the object columns, setting all object values for each column
            for obname, cols in self.col_dict.items():
                if obname==cpmeas.IMAGE or obname==cpmeas.EXPERIMENT:
                    continue
                for _, feature, ftype in cols:
                    feature_name = "%s_%s"%(obname, feature)
                    values = measurements.get_measurement(obname, feature, index)
                    values[np.logical_not(np.isfinite(values))] = 0
                    nvalues = np.product(values.shape)
                    if (nvalues < max_count):
                        sys.stderr.write("Warning: too few measurements for %s in image set #%d, got %d, expected %d\n"%(feature_name,image_number,nvalues,max_count))
                        new_values = np.zeros(max_count, dtype=values.dtype)
                        new_values[:nvalues] = values.flatten()
                        values = new_values
                    elif nvalues > max_count:
                        sys.stderr.write("Warning: too many measurements for %s in image set #%d, got %d, expected %d\n"%(feature_name,image_number,nvalues,max_count))
                        values = values[:max_count]
                    for i in xrange(max_count):
                        object_rows[i,self.object_col_order[feature_name]] = (values[i], cpmeas.COLTYPE_FLOAT)
        
        # wrap non-numeric types in quotes
        image_row_formatted = [(dtype in [cpmeas.COLTYPE_FLOAT, cpmeas.COLTYPE_INTEGER]) and
                               str(val) or "'%s'"%MySQLdb.escape_string(str(val)) 
                               for val, dtype, colname in image_row]
        
        image_table = self.get_table_prefix()+'Per_Image'
        object_table = self.get_table_prefix()+'Per_Object'
        
        stmt = ('INSERT INTO %s (%s) VALUES (%s)' % 
                (image_table, 
                 ','.join([colname for val, dtype, colname in image_row]),
                 ','.join([str(v) for v in image_row_formatted])))
        execute(self.cursor, stmt)
        stmt = ('INSERT INTO %s (%s) VALUES (%s)'%
                (object_table,
                 ','.join(object_cols),
                 ','.join(['%s']*len(object_cols))))

        # Write 25 rows at a time (to get under the max_allowed_packet limit)
        for i in range(0,len(object_rows), 25):
            my_rows = object_rows[i:min(i+25, len(object_rows))]
            self.cursor.executemany(stmt,[ [ str(v) for v,t in ob_row] 
                                           for ob_row in my_rows])
        self.connection.commit()
        
    
    def write_properties(self, workspace):
        """Write the CellProfiler Analyst properties file"""
        #
        # Find the primary object
        #
        for object_name in workspace.measurements.get_object_names():
            if object_name == 'Image':
                continue
            if self.ignore_object(object_name):
                continue
        supposed_primary_object = object_name
        #
        # Find all images that have FileName and PathName
        #
        image_names = []
        for feature in workspace.measurements.get_feature_names('Image'):
            match = re.match('^FileName_(.+)$',feature)
            if match:
                image_names.append(match.groups()[0])
        
        if self.db_type==DB_SQLITE:
            name = os.path.splitext(self.sqlite_file.value)[0]
        else:
            name = self.db_name
        filename = '%s.properties'%(name)
        path = os.path.join(self.get_output_directory(), filename)
        fid = open(path,'wt')
        date = datetime.datetime.now().ctime()
        db_type = (self.db_type == DB_MYSQL and 'mysql') or (self.db_type == DB_SQLITE and 'sqlite') or 'oracle_not_supported'
        db_port = (self.db_type == DB_MYSQL and 3306) or (self.db_type == DB_ORACLE and 1521) or ''
        db_host = 'imgdb01'
        db_pwd  = ''
        db_name = self.db_name
        db_user = 'cpuser'
        db_sqlite_file = (self.db_type == DB_SQLITE and self.get_output_directory()+'/'+self.sqlite_file.value) or ''
        if self.db_type != DB_SQLITE:
            db_info =  'db_type      = %(db_type)s\n'%(locals())
            db_info += 'db_port      = %(db_port)d\n'%(locals())
            db_info += 'db_host      = %(db_host)s\n'%(locals())
            db_info += 'db_name      = %(db_name)s\n'%(locals())
            db_info += 'db_user      = %(db_user)s\n'%(locals())
            db_info += 'db_passwd    = %(db_pwd)s'%(locals())
        else:
            db_info =  'db_type         = %(db_type)s\n'%(locals())
            db_info += 'db_sqlite_file  = %(db_sqlite_file)s'%(locals())
        
        
        spot_tables = '%sPer_Image'%(self.get_table_prefix())
        cell_tables = '%sPer_Object'%(self.get_table_prefix())
        unique_id = 'ImageNumber'
        object_count = 'Image_Count_%s'%(supposed_primary_object)
        object_id = 'ObjectNumber'
        cell_x_loc = '%s_Location_Center_X'%(supposed_primary_object)
        cell_y_loc = '%s_Location_Center_Y'%(supposed_primary_object)
        image_channel_file_names = ','.join(['Image_FileName_%s'%(name) for name in image_names])+','
        image_channel_file_paths = ','.join(['Image_PathName_%s'%(name) for name in image_names])+','
        image_channel_names = ','.join(image_names)+','
        if len(image_names) == 1:
            image_channel_colors = 'gray,'
        else:
            image_channel_colors = 'red,green,blue,cyan,magenta,yellow,gray,none,none,none,'
        # TODO: leave blank if image files are local  
        image_url = 'http://imageweb/images/CPALinks'
        contents = """#%(date)s
# ==============================================
#
# Classifier 2.0 properties file
#
# ==============================================

# ==== Database Info ====
%(db_info)s

# ==== Database Tables ====
image_table   = %(spot_tables)s
object_table  = %(cell_tables)s

# ==== Database Columns ====
image_id      = %(unique_id)s
object_id     = %(object_id)s
cell_x_loc    = %(cell_x_loc)s
cell_y_loc    = %(cell_y_loc)s

# ==== Image Path and File Name Columns ====
# Here you specify the DB columns from your "image_table" that specify the image paths and file names.
# NOTE: These lists must have equal length!
image_channel_paths = %(image_channel_file_paths)s
image_channel_files = %(image_channel_file_names)s

# Give short names for each of the channels (respectively)...
image_channel_names = %(image_channel_names)s

# ==== Image Accesss Info ====
image_url_prepend = %(image_url)s

# ==== Dynamic Groups ====
# Here you can define groupings to choose from when classifier scores your experiment.  (eg: per-well)
# This is OPTIONAL, you may leave "groups = ".
# FORMAT:
#   groups     =  comma separated list of group names (MUST END IN A COMMA IF THERE IS ONLY ONE GROUP)
#   group_XXX  =  MySQL select statement that returns image-keys and group-keys.  This will be associated with the group name "XXX" from above.
# EXAMPLE GROUPS:
#   groups               =  Well, Gene, Well+Gene,
#   group_SQL_Well       =  SELECT Per_Image_Table.TableNumber, Per_Image_Table.ImageNumber, Per_Image_Table.well FROM Per_Image_Table
#   group_SQL_Gene       =  SELECT Per_Image_Table.TableNumber, Per_Image_Table.ImageNumber, Well_ID_Table.gene FROM Per_Image_Table, Well_ID_Table WHERE Per_Image_Table.well=Well_ID_Table.well
#   group_SQL_Well+Gene  =  SELECT Per_Image_Table.TableNumber, Per_Image_Table.ImageNumber, Well_ID_Table.well, Well_ID_Table.gene FROM Per_Image_Table, Well_ID_Table WHERE Per_Image_Table.well=Well_ID_Table.well

groups  =  

# ==== Image Filters ====
# Here you can define image filters to let you select objects from a subset of your experiment when training the classifier.
# This is OPTIONAL, you may leave "filters = ".
# FORMAT:
#   filters         =  comma separated list of filter names (MUST END IN A COMMA IF THERE IS ONLY ONE FILTER)
#   filter_SQL_XXX  =  MySQL select statement that returns image keys you wish to filter out.  This will be associated with the filter name "XXX" from above.
# EXAMPLE FILTERS:
#   filters           =  EMPTY, CDKs,
#   filter_SQL_EMPTY  =  SELECT TableNumber, ImageNumber FROM CPA_per_image, Well_ID_Table WHERE CPA_per_image.well=Well_ID_Table.well AND Well_ID_Table.Gene="EMPTY"
#   filter_SQL_CDKs   =  SELECT TableNumber, ImageNumber FROM CPA_per_image, Well_ID_Table WHERE CPA_per_image.well=Well_ID_Table.well AND Well_ID_Table.Gene REGEXP 'CDK.*'

filters  =  

# ==== Meta data ====
# What are your objects called?
# FORMAT:
#   object_name  =  singular object name, plural object name,
object_name  =  cell, cells,

# ==== Excluded Columns ====
# DB Columns the classifier should exclude:
classifier_ignore_substrings  =  table_number_key_column, image_number_key_column, object_number_key_column

# ==== Other ====
# Specify the approximate diameter of your objects in pixels here.
image_tile_size   =  50

# ==== Internal Cache ====
# It shouldn't be necessary to cache your images in the application, but the cache sizes can be set here.
# (Units = 1 image. ie: "image_buffer_size = 100", will cache 100 images before it starts replacing old ones.
image_buffer_size = 1
tile_buffer_size  = 1
image_channel_colors = %(image_channel_colors)s
"""%(locals())
        fid.write(contents)
        fid.close()
        
    def get_file_path_width(self, workspace):
        """Compute the file name and path name widths needed in table defs"""
        m = workspace.measurements
        #
        # Find the length for the file name and path name fields
        #
        FileNameWidth = 128
        PathNameWidth = 128
        image_features = m.get_feature_names('Image')
        for feature in image_features:
            if feature.startswith('FileName'):
                names = m.get_all_measurements('Image',feature)
                FileNameWidth = max(FileNameWidth, np.max(map(len,names)))
            elif feature.startswith('PathName'):
                names = m.get_all_measurements('Image',feature)
                PathNameWidth = max(PathNameWidth, np.max(map(len,names)))
        return FileNameWidth, PathNameWidth
    
    def get_output_directory(self):
        if (self.use_default_output_directory.value or
            self.output_directory == cps.DO_NOT_USE):
            return cpp.get_default_output_directory()
        elif self.output_directory.value.startswith("."+os.path.sep):
            return os.path.join(cpp.get_default_output_directory(),
                                self.output_directory.value[2:])
        else:
            return self.output_directory.value
    
    def get_table_prefix(self):
        if self.want_table_prefix.value:
            return self.table_prefix.value
        return ""
    
class ColumnNameMapping:
    """Represents a mapping of feature name to column name"""
    
    def __init__(self,max_len=64):
        self.__dictionary = {}
        self.__mapped = False
        self.__max_len = max_len
    
    def add(self,feature_name):
        """Add a feature name to the collection"""
        
        self.__dictionary[feature_name] = feature_name
        self.__mapped = False
    
    def __getitem__(self,feature_name):
        """Return the column name for a feature"""
        if not self.__mapped:
            self.do_mapping()
        return self.__dictionary[feature_name]
    
    def keys(self):
        return self.__dictionary.keys()
    
    def values(self):
        if not self.__mapped:
            self.do_mapping()
        return self.__dictionary.values()
    
    def do_mapping(self):
        """Scan the dictionary for feature names > max_len and shorten"""
        reverse_dictionary = {}
        problem_names = []
        for key,value in self.__dictionary.iteritems():
            reverse_dictionary[value] = key
            if len(value) > self.__max_len:
                problem_names.append(value)
        
        for name in problem_names:
            key = reverse_dictionary[name]
            orig_name = name
            # remove vowels 
            to_remove = len(name)-self.__max_len
            remove_count = 0
            for to_drop in (('a','e','i','o','u'),
                            ('b','c','d','f','g','h','j','k','l','m','n',
                             'p','q','r','s','t','v','w','x','y','z'),
                            ('A','B','C','D','E','F','G','H','I','J','K',
                             'L','M','N','O','P','Q','R','S','T','U','V',
                             'W','X','Y','Z')):
                for index in range(len(name)-1,-1,-1):
                    if name[index] in to_drop:
                        name = name[:index]+name[index+1:]
                        remove_count += 1
                        if remove_count == to_remove:
                            break
                if remove_count == to_remove:
                    break

            while name in reverse_dictionary.keys():
                # if, improbably, removing the vowels hit an existing name
                # try deleting random characters
                name = orig_name
                while len(name) > self.__max_len:
                    index = int(random.uniform(0,len(name)))
                    name = name[:index]+name[index+1:]
            reverse_dictionary.pop(orig_name)
            reverse_dictionary[name] = key
            self.__dictionary[key] = name
