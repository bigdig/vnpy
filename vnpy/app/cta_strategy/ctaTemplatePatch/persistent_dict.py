import pickle
import os
import sys
import atexit
import time
from datetime import datetime
        
class BaseDict(dict):
    def __init__(self, id = 0, last_save_time = 0):
        self.id = id
        self.last_save_time = last_save_time
        self.n_modif_since_saved = 0

class PersistentDict(object):
    db_file_prefix = 'db.'
    db_file_extension = '.pkl'

    def __init__(self, file_basename, file_path = './', n_modif_before_save = 10, 
        max_entries_per_dict = 100, max_dicts_on_ram = 2, save_at_exit = True
    ):
        self.file_basename = file_basename
        self.file_path = file_path
        self.n_modif_before_save = n_modif_before_save
        self.max_entries_per_dict = max_entries_per_dict
        self.max_dicts_on_ram = max_dicts_on_ram
        self.save_at_exit = save_at_exit
        self.save_anyway = False
        self.save_general_properties = True
        self.dicts_on_ram = []
        self.key_dict_id = {} # key: dict_id --> HAS ALL THE KEYS
        self.n_of_dicts = 0 # total numbers of dicts (including non-RAM)
        self.dicts_len_array = [] # to know quickly which sub-dict has space to insert (including non-RAM)
        atexit.register(self.__atexit)

    def __atexit(self):
        if self.save_at_exit:
            self.save_anyway = True
            #print('Saving at exit: ' + str(self.file_basename))
            self.save()

    def save(self):
        if self.save_general_properties or self.save_anyway:
            temp = self.dicts_on_ram
            self.dicts_on_ram = [] # don't want to save the sub-dicts on the properties file
            with open(self.file_path + self.db_file_prefix + str(self.file_basename) + self.db_file_extension, 'wb') as f:
                pickle.dump(self.__dict__, f, pickle.HIGHEST_PROTOCOL)
            self.dicts_on_ram = temp
        for d in self.dicts_on_ram:
            self.save_dict(d, self.save_anyway) # we save them separately


    def load(self):
        try:
            with open(self.file_path + self.db_file_prefix + str(self.file_basename) + self.db_file_extension, 'rb') as f:
                dict = pickle.load(f)
                self.__dict__ = dict
            self.save_anyway = False
        except IOError:
            print("Missing data files for the db: " + str(self.file_basename))
            #self.save_at_exit = False
            #sys.exit(1)

    def save_dict(self, dict, force_save):
        if dict.n_modif_since_saved >= self.n_modif_before_save or force_save:
            dict.n_modif_since_saved = 0
            dict.last_save_time = time.time()
            with open(self.file_path + self.db_file_prefix + str(self.file_basename) + str(dict.id) + self.db_file_extension, 'wb') as f:
                pickle.dump(dict, f, pickle.HIGHEST_PROTOCOL)

    def load_dict(self, dict_id):
        try:
            # requieres len(dicts_on_ram) < max_dicts_on_ram to keep the invariant
            with open(self.file_path + self.db_file_prefix + str(self.file_basename) + str(dict_id) + self.db_file_extension, 'rb') as f:
                dict = pickle.load(f)
                return dict
        except IOError:
            print("Missing data files for the db: " + str(self.file_basename) + str(dict_id))
            #self.save_at_exit = False
            #sys.exit(1)

    def __getstate__(self):
        # This method is only call when the PersistentDict is "inside" another obj
        # and that obj is pickled.
        self.save()
        return self.file_path, self.file_basename

    def __setstate__(self, file_path_and_basename_tuple):
        # This method is only call when the PersistentDict is "inside" another obj
        # and that obj is unpickled.
        self.file_path, self.file_basename = file_path_and_basename_tuple
        self.load()
        # As it was "load" by pickle, the __init__() wasn't executed, register atexit handler
        atexit.register(self.__atexit)

    def add_item_dict(self, dict, key, value):
        # Requires len(dict) < self.max_entries_per_dict
        dict[key] = value
        dict.n_modif_since_saved = dict.n_modif_since_saved + 1
        self.key_dict_id[key] = dict.id
        self.dicts_len_array[dict.id] = self.dicts_len_array[dict.id] + 1
        self.save_dict(dict, force_save = False)

    def add_dict_to_ram(self, dict):
        if not len(self.dicts_on_ram) < self.max_dicts_on_ram:
            self.save_dict(self.dicts_on_ram[0], force_save = True) # force save before removing it
            self.dicts_on_ram.pop(0) # FIFO
        self.dicts_on_ram.append(dict)

    def add_new_dict(self):
        dict = BaseDict(id = self.n_of_dicts)
        self.n_of_dicts = self.n_of_dicts + 1
        self.dicts_len_array.append(0)
        return dict

    def __setitem__(self, key, value):
        if key in self.key_dict_id:
            dict_id = self.key_dict_id[key]

            for d in self.dicts_on_ram:
                if d.id == dict_id:
                    self.add_item_dict(d, key, value)
                    return

            self.add_dict_to_ram(self.load_dict(dict_id))
            self.add_item_dict(self.dicts_on_ram[len(self.dicts_on_ram) - 1], key, value)
        else:
            # First try to define on RAM (to do it quickly)
            for d in self.dicts_on_ram:
                if len(d) < self.max_entries_per_dict:
                    self.add_item_dict(d, key, value)
                    return
            # Look for a candidate in disc with space: choose the first one that fits in.
            # This algorithm may be improved: choose the dict with less entries, etc...
            for i in range(0, self.n_of_dicts):
                if self.dicts_len_array[i] < self.max_entries_per_dict:
                    self.add_dict_to_ram(self.load_dict(i))
                    self.add_item_dict(self.dicts_on_ram[len(self.dicts_on_ram) - 1], key, value)
                    return
            # Create a new dict (there are no dicts or all of them are full)
            self.add_dict_to_ram(self.add_new_dict())
            self.add_item_dict(self.dicts_on_ram[len(self.dicts_on_ram) - 1], key, value)

    def rm_item_dict(self, dict, key):
        del dict[key]
        del self.key_dict_id[key]
        dict.n_modif_since_saved = dict.n_modif_since_saved + 1
        self.dicts_len_array[dict.id] = self.dicts_len_array[dict.id] - 1
        self.save_dict(dict, force_save = False)

    def __delitem__(self, key):
        if key in self.key_dict_id:
            dict_id = self.key_dict_id[key]
            for d in self.dicts_on_ram:
                if d.id == dict_id:
                    self.rm_item_dict(d, key)
                    return
            self.add_dict_to_ram(self.load_dict(dict_id))
            self.rm_item_dict(self.dicts_on_ram[len(self.dicts_on_ram) - 1], key)

    def get_item_dict(self, dict, key):
        return dict[key]

    def __getitem__(self, key):
        if key in self.key_dict_id:
            dict_id = self.key_dict_id[key]
            for d in self.dicts_on_ram:
                if d.id == dict_id:
                    return self.get_item_dict(d, key)
            self.add_dict_to_ram(self.load_dict(dict_id))
            return self.get_item_dict(self.dicts_on_ram[len(self.dicts_on_ram) - 1], key)

    def get(self, key, default_value):
        if key not in self.keys():
            return default_value
        return self.__getitem__(key)

    def __iter__(self):
        return self.key_dict_id.__iter__()

    def keys(self):
        return self.key_dict_id.keys()

    def next(self):
        return self.key_dict_id.next()

    def items(self):
        # it could be done in a more efficient way: first putting (key, value) of the RAM dicts
        # and then the others...
        res = []
        for k in self.keys():
            res.append((k,self[k]))
        return res

    def __len__(self):
        return len(self.key_dict_id)

    def debug_print_general_info(self):
        print('DB Name: ' + str(self.file_basename) + ' -- Num of dicts: ' + str(self.n_of_dicts) + ' -- Len: ' + str(len(self)))
        print('Dicts on RAM[max=' + str(self.max_dicts_on_ram) + ']: ' + str([d.id for d in self.dicts_on_ram]))
        for d in self.dicts_on_ram:
            print('Dict n: ' + str(d.id) + ' -- ' + self.debug_last_save_time(d) + ' -- [max_records=' + str(self.max_entries_per_dict) + ']')
            print(d)

    def debug_print_key_values(self):
        print('[' + str(self.file_basename) + ']Items:')
        print(self.items())

    def debug_print_key_dict_id(self):
        print('[' + str(self.file_basename) + ']KeyDictId:')
        print(self.key_dict_id)

    def debug_last_save_time(self, dict):
        return str(datetime.fromtimestamp(int(dict.last_save_time)).strftime('%H:%M:%S,%d-%m-%Y'))

    def debug(self):
        print('')
        print('+------------------------------------+')
        print('|************************************|')
        print('|                DEBUG               |')
        print('|************************************|')
        print('+------------------------------------+')
        self.debug_print_key_dict_id()
        self.debug_print_key_values()
        self.debug_print_general_info()
        print('')