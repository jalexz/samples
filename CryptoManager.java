/****************************************************************************
 * This is a snippet from an old project I made for my Distributed Systems  *
 * course back in 2008 when I was a student at Politecnico di Milano.	    *
 * It is a module that implements Diffie-Hellmann key exchange protocol for * 
 * a group chat.															*
 ****************************************************************************/
 
package it.polimi.distsys0708.demo.gdh.groupmember;

import it.polimi.distsys0708.demo.gdh.utils.GDHParams;
import it.polimi.distsys0708.demo.gdh.utils.IntermediateValue;
import it.polimi.distsys0708.demo.gdh.utils.KAMValues;

import java.math.BigInteger;
import java.security.InvalidAlgorithmParameterException;
import java.security.InvalidKeyException;
import java.security.Key;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.HashSet;
import java.util.Set;
import java.util.logging.Logger;

import javax.crypto.BadPaddingException;
import javax.crypto.Cipher;
import javax.crypto.IllegalBlockSizeException;
import javax.crypto.KeyAgreement;
import javax.crypto.NoSuchPaddingException;
import javax.crypto.SecretKey;
import javax.crypto.spec.DHParameterSpec;

/**
 * Manages encryption and key agreement in a {@link GroupMemberImpl}.
 * The funcionalities implemented by this class are the following:
 * <ul>
 *   <li> Key agreement initialization with GDH parameters of the current group, 
 *        through {@link #init(GDHParams)} method;
 *   <li> Key agreement protocol execution through methods 
 *        {@link #doUpflow(KAMValues, BigInteger, boolean)}, 
 *        {@link #doDownflow(KAMValues, BigInteger)};
 *   <li> Messages encryption/decryption through methods
 *        {@link #decryptMessage(byte[])} and {@link #encryptMessage(String)}.
 * </ul>
 * Note: in this documentation we will refer to KAMValues objects
 * like they were key agreement messages, even if they are just a part of them
 * (although the most important).
 */
public class CryptoManager {
	
    /* Key pair generator (public/private). */
    private final KeyPairGenerator key_pair_generator;
	
    /* Key agreement protocol implementation. */
    private final KeyAgreement key_agreement;
    
    /* Input cipher (message encryption). */
    private Cipher input_cipher;
    
    /* Output cipher (message decryption). */
    private Cipher output_cipher;
    
    /* GDH.2 protocol parameters. */
    private GDHParams gdh_params;
    
    /* Public/private key pair. */
    private KeyPair key_pair;
    
    /* Last upflow message received. */
    private KAMValues last_upflow_recvd;
	
    /* Class logger. */
    private final Logger logger;
    
	/**
	 * Class constructor.
	 * Get a key pair generator and a key agreement protocol implementation for
	 * the Diffie-Hellman algorithm.
	 * 
	 * @throws NoSuchAlgorithmException if an error occurs during initialization.
	 */
	public CryptoManager() throws NoSuchAlgorithmException {
		
		/* Get the class logger. */
		logger = Logger.getLogger(this.getClass().getName());
		logger.finest("Logger della classe " + this.getClass().getName() + " pronto.");
		
		/* Get the key pair generator for the Diffie-Hellman algorithm. */
		key_pair_generator = KeyPairGenerator.getInstance("DH");
		logger.finest("Ottenuto il generatore di coppie di chiavi per Diffie-Hellman.");
		
		/* Get the implementation of the key agreement for the Diffie-Hellman protocol. */
		key_agreement = KeyAgreement.getInstance("DH");
		logger.finest("Ottenuto l'esecutore del protocollo di key agreement per Diffie-Hellman.");
		
		/* These fileds will be initialized later in the init() method. */
		input_cipher = null;
		output_cipher = null;
		gdh_params = null;
		key_pair= null;
		last_upflow_recvd = null;
		
	}
	
	/**
	 * Initializes cryptographics elements that are dependent from the particular
	 * GDH parameters used by each group.
	 * A {@link CryptoManager} must be reinitialized with this method
	 * each time that group's GDH.2 parameters change.
	 * @param gdhp GDH.2 protocol parameters for cryptographic initialization.
	 * @throws NoSuchAlgorithmException if an error occurs during initialization.
	 * @throws NoSuchPaddingException if an error occurs during initialization.
	 * @throws InvalidAlgorithmParameterException if an error occurs during initialization.
	 * @throws InvalidKeyException if an error occurs during initialization.
	 */
	public synchronized void init(GDHParams gdhp) throws NoSuchAlgorithmException, NoSuchPaddingException, InvalidAlgorithmParameterException, InvalidKeyException {
		
		gdh_params = gdhp;
		logger.finest("Inizializzazione della crittografia con i seguenti parametri:\n" +
				gdhp);
		
		/* Get input/output ciphers for the encryption algorithm
		 * specified in the GDH.2 parameters. */
		input_cipher = Cipher.getInstance(gdhp.encryption_algorithm);
		logger.finest("Ottenuto il cifrario di input.");
	    output_cipher = Cipher.getInstance(gdhp.encryption_algorithm);
	    logger.finest("Ottenuto il cifrario di output.");
		
	    /* Initializes the key pair generator with the GDH.2 parameters. */
	    key_pair_generator.initialize(
				new DHParameterSpec( gdh_params.p, gdh_params.g, gdh_params.l )
		);
		logger.finest("Generatore di coppie di chiavi pubblica/privata inizializzato.");
	    
	    /* Generates the key pair. */
		key_pair = key_pair_generator.generateKeyPair();
		logger.finest("Coppia di chiavi pubblica/privata generata.");
		
		/* Initializes the key agreement implementation with the private key. */
		key_agreement.init(key_pair.getPrivate());
		logger.finest("Esecutore del key agreement inizializzato con la chiave privata.");
		
		/* After every initialization, the last upflow message received is cleared. */
		last_upflow_recvd = null;
		
	}
	
	/**
	 * Encrypt a message using the current key.
	 * @param the message to encrypt.
	 * @return a byte array containing the encrypted message.
	 * @throws IllegalBlockSizeException if an error occurs during message encryption.
	 * @throws BadPaddingException if an error occurs during message encryption.
	 * @throws IllegalStateException if the output cipher wasn't correctly initialized.
	 */
	public synchronized byte[] encryptMessage(String plain_msg) throws IllegalBlockSizeException, BadPaddingException, IllegalStateException {
		
		if (output_cipher == null)
			throw new IllegalStateException("Il cifrario di output non e' stato ancora creato.");
		
		return output_cipher.doFinal(plain_msg.getBytes());
		
	}
	
	/**
	 * Decrypt a message using the current key. 
	 * @param encrypted_msg message to decrypt.
	 * @return the decrypted message.
	 * @throws IllegalBlockSizeException if an error occurs during message decryption.
	 * @throws BadPaddingException if an error occurs during message encryption.
	 * @throws IllegalStateException if the input cipher wasn't correctly initialized.
	 */
	public synchronized String decryptMessage(byte[] encrypted_msg) throws IllegalBlockSizeException, BadPaddingException, IllegalStateException {
		
		if (input_cipher == null)
			throw new IllegalStateException("Il cifrario di input non e' stato ancora creato.");
		
		return new String(input_cipher.doFinal(encrypted_msg));
		
	}
	
	/**
	 * Do one step of the upflow phase of the key agreement algorithm GDH.2.
	 * The step can be executed as:
	 *  <ul>
	 *    <li> first member: creates the initial key agreement message to be sent through
	 *         the members chain.
	 *    <li> intermediate member: creates an intermediate key agreement message from the
	 *         received one. The new message will follow on the memebers chain.
	 *    <li> last member: the group key is generated and a final key agreement message
         *         is created. This will be broadcasted to the other group members to allow
         *         them to generate the same group key.
	 * @param kam previous key agreement message. If <code>null</code>, the upflow step will
	          be executed as the first member.
	 * @param member_id id of the owner of this upflow step.
	 * @param last <code>true</code> if this is the last upflow step.
	 * @return the key agreement message for the next step.
	 * @throws InvalidKeyException if an error occurs during this upflow step.
	 * @throws IllegalStateException if the step is executed in a cryptographic state not 
	           correctly initialized (e.g. the key pair was not yet generated).
	 * @throws NoSuchAlgorithmException if an error occurs during this upflow step.
	 * @throws NullPointerException if <code>member_id</code> is <code>null</code>.
	 * @throws IllegalArgumentException if the content of <code>kam</code> is not valid for
	 *         the current upflow step.
	 */
	public synchronized KAMValues doUpflow(KAMValues kam, BigInteger member_id, boolean last) throws InvalidKeyException, IllegalStateException, NoSuchAlgorithmException, NullPointerException, IllegalArgumentException {
		
		if (member_id == null)
			throw new NullPointerException("Specificato un id membro non valido: null.");
		
		if (kam == null && last)
			throw new IllegalArgumentException("I parametri 'kam' e 'last' hanno valori " +
					"incompatibili: kam = null e last = true. Il passo di upflow non" +
					"puo' essere contemporaneament iniziale e finale.");
		
		/* Saves the last received upflow message. */
		last_upflow_recvd = (kam != null ? kam.clone() : null);
		
		/* The new key agreement message. */
		KAMValues result = null;
		
		if (!last) {
			if (kam == null) {
				/* Starts the upflow phase. */
				result = startUpflow(member_id);
			}
			else {
				/* Continues the upflow phase. */
				result = continueUpflow(kam, member_id);
			}
		}
		else {
			/* Ends the upflow phase. */
			if (kam.cardinal_value == null)
				throw new IllegalArgumentException("Specificato un key agreement message non valido: il valore cardinale e' null.");
			result = endUpflow(kam, member_id);
		}
		
		return result;
	}

	/**
	 * Redo a step of the upflow phase of the GDH.2 key agreement protocol
	 * (i.e. when a new member joins or an old member leaves the group).
	 * As a preliminary step, a new key pair is generated to be used in the
	 * agreement process. If necessary, the steps in order to exclude the specified
	 * group members are executed.
	 * The step can be executed as:
	 *  <ul>
	 *    <li> intermediate member: creates an intermediate key agreement message from the
	 *         received one. The new message will follow on the memebers chain.
	 *    <li> last member: the group key is generated and a final key agreement message
         *         is created. This will be broadcasted to the other group members to allow
         *         them to generate the same group key.
	 *  </ul>
	 * @param member_id id of the owner of this upflow step.
	 * @param last <code>true</code> if this is the last upflow step.
	 * @param excluded_members a set of group member's id that will be exluded from the
	 *        next key agreement phases. It can be <code>null</code>.
	 * @return the key agreement message for the next phase.
	 * @throws InvalidKeyException if an error occurs during this upflow step.
	 * @throws IllegalStateException if the step is executed in a cryptographic state not 
	           correctly initialized (e.g. the key pair was not yet generated).
	 * @throws NoSuchAlgorithmException if an error occurs during this upflow step.
	 * @throws NullPointerException if <code>member_id</code> is <code>null</code>.
	 */
	public synchronized KAMValues redoUpflow(BigInteger member_id, boolean last, Set<BigInteger> excluded_members) throws InvalidKeyException, IllegalStateException, NoSuchAlgorithmException, NullPointerException {
		
		if (member_id == null)
			throw new NullPointerException("Specificato un id membro non valido: null.");
		
		/* If no previous upflow message was received, throws an excpetion. */
		if (last_upflow_recvd == null) {
			throw new IllegalStateException("Impossibile rieseguire l'upflow: nessun messaggio di upflow e' stato precedentemente ricevuto.");
		}
		
		/* Removes the specified group members from the next key agreement phases. */
		if (excluded_members != null) {
			logger.fine("Saranno esclusi dal key agreement i seguenti membri: " + excluded_members);
			Deque<IntermediateValue> d_tmp = 
				new ArrayDeque<IntermediateValue>(last_upflow_recvd.intermediate_values);
			last_upflow_recvd.excludeMembers(excluded_members);
			d_tmp.removeAll(last_upflow_recvd.intermediate_values);
			logger.finer("Sono stati rimossi i seguenti valori intermedi: " + d_tmp);
		}
		
		logger.finest("Ultimo messaggio di upflow ricevuto: " + last_upflow_recvd);
		
		/* Generates a new key pair before executing the upflow step. */
		key_pair = key_pair_generator.generateKeyPair();
		logger.finest("Coppia di chiavi pubblica/privata generata.");

		/* Initializes the key agreement implementation with the private key. */
		key_agreement.init(key_pair.getPrivate());
		logger.finest("Esecutore del key agreement inizializzato con la chiave privata.");
			
		/* The new key agreement message. */
		KAMValues result = null;
		
		if (!last) {
			/* Continues the upflow phase. */
			result = continueUpflow(last_upflow_recvd.clone(), member_id);
		}
		else {
			/* Ends the upflow phase. */
			if (last_upflow_recvd.cardinal_value == null)
				throw new IllegalStateException("Impossibile effettuare la fase finale " +
						"di upflow: l'ultimo valore di upflow memorizzato ha un valore " +
						"cardinale pari a null.");
			result = endUpflow(last_upflow_recvd.clone(), member_id);
		}
		
		return result;
		
	}
	
	/**
	 * Do the downflow phase of the GDH.2 key agreement algorithm, i.e. the group key
	 * is securely generated by each group member using the received key agreement message.
	 * @param kam the received key agreement message.
	 * @throws InvalidKeyException if an error occurs during the group key generation.
	 * @throws IllegalStateException if the downflow step is executed in an invalid cryptographic state.
	 * @throws NoSuchAlgorithmException if an error occurs during the group key generation.
	 * @throws NullPointerException if <code>kam</code> is <code>null</code>.
	 * @throws IllegalArgumentException if the content of <code>kam</code> can't be used to execute
	 *         the current downflow step.
	 */
	public synchronized void doDownflow(KAMValues kam) throws InvalidKeyException, IllegalStateException, NoSuchAlgorithmException, NullPointerException, IllegalArgumentException {
		
		if (kam == null)
			throw new NullPointerException("Specificato un key agreement message non valido: null.");
		else if(kam.cardinal_value == null)
			throw new IllegalArgumentException("Specificato un key agreement message non valido: il valore cardinale e' null.");
		
		/* Computes the new group key. */
		computeSecretKey(kam.cardinal_value.value);
		
	}
		
	/**
	 * Execute the upflow step as the last member:
	 * computes the new set of intermediate values by raising to its private key all the previous
	 * intermediate values, then, computes the group key using the previous cardinal value.
	 * I/O ciphers are initialized to be used with the new group key.
	 * @param kam messaggio di key agreement precedente. Se null, viene eseguito il passo
	 *        iniziale di upflow.
	 * @param member_id identificativo del membro del gruppo che sta effettuando il passo 
	 *        corrente di upflow.
	 * @return the key agreement message to be used with the next phase.
	 * @throws InvalidKeyException if an error occurs during the upflow step.
	 * @throws IllegalStateException if the step is executed in a cryptographic state not 
	 *         correctly initialized (e.g. the key pair was not yet generated).
	 * @throws NoSuchAlgorithmException if an error occurs during the upflow step.
	 */
	private KAMValues endUpflow(KAMValues kam, BigInteger member_id) throws InvalidKeyException, IllegalStateException, NoSuchAlgorithmException {
		
		if (key_pair == null)
			throw new IllegalStateException("Nessuna coppia di chiavi pubblica/privata e' stata ancora generata.");
		
		KAMValues result; 
		IntermediateValue iv_tmp;
		Key k_tmp;
		Set<BigInteger> s_tmp;
		
		/* The new intermediate values set will have at most one element more. */
		Deque<IntermediateValue> new_int_val = 
			new ArrayDeque<IntermediateValue>(kam.intermediate_values.size()+1);

		if (kam.intermediate_values.size() == 0) {
			/* If there were no previous intermediate values, inserts the public key as new
			 * intermediate value. */
			k_tmp = key_pair.getPublic();
			s_tmp = new HashSet<BigInteger>();
			s_tmp.add(member_id);
			iv_tmp = new IntermediateValue(s_tmp, k_tmp);
			new_int_val.addLast(iv_tmp);
			logger.finer("Aggiunto il nuovo valore intermedio " + iv_tmp);
		}
		for (int i = 0; kam.intermediate_values.size() > 0; i++) {
			/* Get an intermediate value. */
			iv_tmp = kam.intermediate_values.removeFirst();
			logger.finer("Estratto il vecchio valore intermedio " + iv_tmp);
			/* Computes the new intermediate value. */
			k_tmp = key_agreement.doPhase(iv_tmp.value, false);
			s_tmp = new HashSet<BigInteger>(iv_tmp.members);
			s_tmp.add(member_id);
			iv_tmp = new IntermediateValue(s_tmp,k_tmp);
			/* Adds the new intermediate value. */
			new_int_val.addLast(iv_tmp);
			logger.finer("Aggiunto il nuovo valore intermedio " + iv_tmp);
		}

		/* Creates the new key agreement message. */
		result = new KAMValues(new_int_val, null);
		
		/* Computes the new group key using the previous cardinal value. */
		computeSecretKey(kam.cardinal_value.value);
		
		return result; 
		
	}

	/**
	 * Computes the key to be used by the group members to encrypt/decrypt their messages.
	 * I/O ciphers will be initialized with this new key.
	 * @param card_val cardinal value to be used in the computation of the new key.
	 * @throws InvalidKeyException if an error occurs during the key generation.
	 * @throws IllegalStateException if an error occurs during the key generation.
	 * @throws NoSuchAlgorithmException if an error occurs during the key generation.
	 */
	private void computeSecretKey(Key card_val) throws InvalidKeyException, IllegalStateException, NoSuchAlgorithmException {
		
		/* Computes the session secret by raising the cardinal value to the private key. */
		key_agreement.doPhase(card_val, true);
		logger.finest("Calcolato il segreto di sessione.");
		
		/* Actual group key generation. */
		SecretKey secret_key = key_agreement.generateSecret(gdh_params.encryption_algorithm);
		logger.fine("Calcolata la nuova chiave simmetrica di gruppo: " + 
				Integer.toHexString(secret_key.hashCode())+ " (" + 
				(secret_key.getEncoded().length*8) + "bit)");
		
		/* I/O ciphers generation. */
		input_cipher.init(Cipher.DECRYPT_MODE, secret_key);
		logger.finest("Cifrario di input inizializzato con la chiave simmetrica.");
		output_cipher.init(Cipher.ENCRYPT_MODE, secret_key);
		logger.finest("Cifrario di output inizializzato con la chiave simmetrica.");
		
	}

	/**
	 * Do the upflow phase as an intermediate member:
	 * computes the new set of intermediate values by raising to its private key all the previous
	 * intermediate values and adding the previous cardinal value, then, and computes the new
	 * cardinal value.
	 * @param kam the previous key agreement message.
	 * @param member_id id of the owner of this upflow step.
	 * @return the new key agreement message.
	 * @throws InvalidKeyException if an error occurs during the upflow step..
	 * @throws IllegalStateException if the step is executed in a cryptographic state not 
	 *         correctly initialized (e.g. the key pair was not yet generated).
	 */
	private KAMValues continueUpflow(KAMValues kam, BigInteger member_id) throws InvalidKeyException, IllegalStateException {
		
		if (key_pair == null)
			throw new IllegalStateException("Nessuna coppia di chiavi pubblica/privata e' stata ancora generata.");
		
		IntermediateValue iv_tmp;
		Key k_tmp;
		HashSet<BigInteger> s_tmp;
		
		/* The new intermediate values set will have at most one element more. */
		Deque<IntermediateValue> new_int_val = 
			new ArrayDeque<IntermediateValue>(kam.intermediate_values.size()+2);

		/* The last cardinal value becomes a new intermediate value. */
		new_int_val.addLast(kam.cardinal_value.clone());
		logger.finer("Aggiunto il nuovo valore intermedio " + kam.cardinal_value);

		if (kam.intermediate_values.size() == 0) {
			/* If there were no previous intermediate values, inserts the public key as new
			 * intermediate value. */
			k_tmp = key_pair.getPublic();
			s_tmp = new HashSet<BigInteger>();
			s_tmp.add(member_id);
			iv_tmp = new IntermediateValue(s_tmp, k_tmp);
			new_int_val.addLast(iv_tmp);
			logger.finer("Aggiunto il nuovo valore intermedio " + iv_tmp);
		}
		for (int i = 0; kam.intermediate_values.size() > 0; i++) {
			/* Get an intermediate value. */
			iv_tmp = kam.intermediate_values.removeFirst();
			logger.finer("Estratto il vecchio valore intermedio " + iv_tmp);
			/* Computes the new intermediate value. */
			k_tmp = key_agreement.doPhase(iv_tmp.value, false);
			s_tmp = new HashSet<BigInteger>(iv_tmp.members);
			s_tmp.add(member_id);
			iv_tmp = new IntermediateValue(s_tmp,k_tmp);
			/* Adds the new intermediate value. */
			new_int_val.addLast(iv_tmp);
			logger.finer("Aggiunto il nuovo valore intermedio " + iv_tmp);
		}
		
		/* Computes the new cardinal value: it is the previous one raised to the 
		 * current private key. */
		k_tmp = key_agreement.doPhase(kam.cardinal_value.value, false);
		s_tmp = new HashSet<BigInteger>(kam.cardinal_value.members);
		s_tmp.add(member_id);
		iv_tmp = new IntermediateValue(s_tmp, k_tmp);
		logger.fine("Calcolato il nuovo valore cardinale: " + iv_tmp);
		
		/* Creates the new key agreement value. */
		return new KAMValues(new_int_val, iv_tmp);
		
	}

	/**
	 * Do the upflow phase as the initial member:
	 * the set of intermediate values is empty, initializes it.
	 * @param member_id id of the owner of this upflow step.
	 * @return the initial key agreement message.
	 * @throws IllegalStateException if the step is executed in a cryptographic state not 
	 *         correctly initialized (e.g. the key pair was not yet generated).
	 */
	private KAMValues startUpflow(BigInteger member_id) throws IllegalStateException {
		
		if (key_pair == null)
			throw new IllegalStateException("Nessuna coppia di chiavi pubblica/privata e' stata ancora generata.");
			
		IntermediateValue iv_tmp;
		Key k_tmp;
		Set<BigInteger> s_tmp;
		
		/* Initializes the set of intermediate values. */
		Deque<IntermediateValue> new_int_val = 
			new ArrayDeque<IntermediateValue>(0);
		logger.finer("Nessun valore intermedio da calcolare.");
		
		/* The initial cardinal value is the current public key. */
		k_tmp = key_pair.getPublic();
		s_tmp = new HashSet<BigInteger>();
		s_tmp.add(member_id);
		iv_tmp = new IntermediateValue(s_tmp, k_tmp); 
		logger.finer("Calcolato il nuovo valore cardinale: " + iv_tmp);
		
		/* Creates the initial key agreement message. */
		return new KAMValues(new_int_val, iv_tmp);
		
	}

}
